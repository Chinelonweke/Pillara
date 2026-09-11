# services/drug_name_resolver.py
#
# WHAT THIS DOES:
# Resolves any drug brand name to its generic name via the RxNorm API.
# RxNorm is the US National Library of Medicine's drug terminology system.
# It contains 100,000+ drugs with all brand names, generic names, and synonyms.
# Free to use — no API key required.
#
# WHY NOT A HARDCODED DICT:
# 10,000+ brand names exist worldwide. A hardcoded dict is unmaintainable.
# RxNorm resolves "Tylenol", "Emzor Paracetamol", "Panadol Extra" all correctly
# without any manual maintenance.
#
# CACHING:
# Results are cached in Redis for 24 hours.
# First lookup: ~200ms (RxNorm API call)
# Subsequent lookups: ~1ms (Redis cache hit)

import httpx
from monitoring.logger import get_logger

logger = get_logger(__name__)

RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"
CACHE_TTL = 86400  # 24 hours


async def resolve_to_generic(drug_name: str, redis=None) -> str:
    """
    Resolves a drug brand name to its generic name via RxNorm.
    Falls back to the original name if RxNorm doesn't recognize it.

    Examples:
        "Tylenol" → "Acetaminophen"
        "Advil"   → "Ibuprofen"
        "Panadol" → "Acetaminophen"
        "metformin" → "metformin" (already generic, returned as-is)
    """
    name_lower = drug_name.lower().strip()
    cache_key = f"rxnorm:generic:{name_lower}"

    # Check Redis cache first
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                resolved = cached.decode()
                logger.debug("rxnorm_cache_hit", drug=drug_name, resolved=resolved)
                return resolved
        except Exception as e:
            logger.debug("rxnorm_cache_read_failed", error=str(e))

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:

            async def rxnorm_lookup(name: str):
                """Call RxNorm and return (rxcui, generic_name) or None."""
                r = await client.get(
                    f"{RXNORM_BASE}/rxcui.json",
                    params={"name": name, "search": 1}
                )
                rxcui_list = r.json().get("idGroup", {}).get("rxnormId", [])
                if not rxcui_list:
                    return None
                rxcui = rxcui_list[0]
                r2 = await client.get(f"{RXNORM_BASE}/rxcui/{rxcui}/properties.json")
                generic = r2.json().get("properties", {}).get("name", name).lower()
                return (rxcui, generic)

            # ── Step 1: Try the full drug name directly ───────────────────
            result = await rxnorm_lookup(drug_name)

            # ── Step 2: Word extraction for Nigerian/African brand names ──
            # Many Nigerian brands follow: "[Manufacturer] [INN] [Dose]"
            # e.g. "Emzor Paracetamol 500mg" → INN is "Paracetamol" (second word)
            #
            # Algorithm (in order):
            # 1. Try EXACT match (search=0) for each candidate word, right-to-left
            #    (INN is typically the last meaningful word, manufacturer is first)
            # 2. If no exact match found anywhere, try FUZZY match right-to-left
            #    (fuzzy/search=1 can match manufacturer names to wrong drugs)
            # This prevents a manufacturer prefix like "Emzor" from fuzzy-matching
            # some unrelated RxNorm concept before the real INN is tried.
            if not result and len(name_lower.split()) > 1:
                import re
                SKIP_WORDS = {
                    'tablet', 'capsule', 'syrup', 'injection', 'suspension',
                    'cream', 'ointment', 'drops', 'plus', 'extra', 'forte',
                    'junior', 'adult', 'night', 'rapid', 'extended', 'release',
                    # Salt/ester suffixes — these resolve to a valid RxNorm rxcui
                    # on their own (e.g. "Sodium", "Tartrate"), so without this
                    # list the right-to-left match would identify the SALT FORM
                    # as the drug instead of the actual active ingredient
                    # (e.g. "Diclofenac Sodium" would resolve to "sodium").
                    'sodium', 'potassium', 'calcium', 'magnesium', 'chloride',
                    'hydrochloride', 'sulfate', 'sulphate', 'tartrate', 'maleate',
                    'succinate', 'citrate', 'phosphate', 'acetate', 'mesylate',
                    'besylate', 'fumarate', 'gluconate', 'bromide', 'dihydrate',
                    'monohydrate', 'trihydrate', 'hydrate',
                }
                words = re.findall(r'[a-zA-Z]{4,}', drug_name)
                candidate_words = [
                    w for w in words
                    if w.lower() != name_lower and w.lower() not in SKIP_WORDS
                ]

                # Pass 1: Exact match across all candidates, right-to-left
                # (INN typically last, manufacturer typically first).
                # IMPORTANT: check every candidate word rather than stopping at the
                # first hit. A name with two independently-resolving ingredient
                # words (e.g. "Amoxicillin Cloxacillin") is a combination product —
                # silently keeping only the first match would misidentify the drug
                # and return confident-looking results about the wrong ingredient.
                exact_matches = []  # [(rxcui, generic_name), ...], deduplicated by generic name
                for word in reversed(candidate_words):
                    try:
                        r = await client.get(
                            f"{RXNORM_BASE}/rxcui.json",
                            params={"name": word, "search": 0}  # exact match
                        )
                        rxcui_list = r.json().get("idGroup", {}).get("rxnormId", [])
                        if rxcui_list:
                            r2 = await client.get(f"{RXNORM_BASE}/rxcui/{rxcui_list[0]}/properties.json")
                            generic = r2.json().get("properties", {}).get("name", word).lower()
                            if generic not in {g for _, g in exact_matches}:
                                exact_matches.append((rxcui_list[0], generic))
                    except Exception as exact_err:
                        logger.debug("rxnorm_exact_word_failed", word=word, error=str(exact_err))

                if len(exact_matches) == 1:
                    rxcui, generic = exact_matches[0]
                    result = (rxcui, generic)
                    logger.info(
                        "rxnorm_word_extraction_exact",
                        original=drug_name,
                        generic=generic,
                        match_type="exact",
                    )
                elif len(exact_matches) > 1:
                    # Combination product — return all resolved ingredients joined,
                    # rather than silently dropping all but one. Downstream (RAG
                    # retrieval metadata filter) will only match a chunk tagged with
                    # this exact combined name, which safely yields "no evidence"
                    # instead of confidently returning info about a single ingredient.
                    combined_generic = "/".join(sorted(g for _, g in exact_matches))
                    result = (exact_matches[0][0], combined_generic)
                    logger.warning(
                        "rxnorm_combination_drug_detected",
                        original=drug_name,
                        ingredients=[g for _, g in exact_matches],
                        combined_generic=combined_generic,
                    )

                # Pass 2: Fuzzy match across all candidates, right-to-left
                # Only runs if exact match found nothing
                if not result:
                    for word in reversed(candidate_words):
                        word_result = await rxnorm_lookup(word)
                        if word_result:
                            result = word_result
                            logger.info(
                                "rxnorm_word_extraction_fuzzy",
                                original=drug_name,
                                matched_word=word,
                                generic=word_result[1],
                                match_type="fuzzy",
                                warning="fuzzy_match_verify_manually",
                            )
                            break

            if not result:
                logger.debug("rxnorm_no_match", drug=drug_name)
                return name_lower

            rxcui, generic_name = result

            logger.info(
                "rxnorm_resolved",
                brand=drug_name,
                generic=generic_name,
                rxcui=rxcui,
            )

            # Cache the result
            if redis:
                try:
                    await redis.setex(cache_key, CACHE_TTL, generic_name)
                except Exception as e:
                    logger.warning("rxnorm_cache_write_failed", error=str(e))

            return generic_name

    except Exception as error:
        logger.warning("rxnorm_lookup_failed", error=str(error))  # drug name omitted — PHI

    # Step 1 + Step 2 both failed — return original name
    # Post-launch: integrate DrugBank Open Data (free, register at go.drugbank.com)
    # to handle compound African brands (Lonart, Ampiclox, Septrin etc.)
    logger.warning(
        "drug_name_unresolved",
        drug=drug_name,
        message="Could not resolve via RxNorm direct lookup or word extraction",
    )
    return name_lower


async def resolve_all_drug_names(drug_names: list, redis=None) -> list:
    """
    Resolves a list of drug names to their generic forms.
    Deduplicates results — "Tylenol" and "acetaminophen" both → "acetaminophen".
    """
    import asyncio
    resolved = await asyncio.gather(*[
        resolve_to_generic(name, redis) for name in drug_names
    ])
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for name in resolved:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique