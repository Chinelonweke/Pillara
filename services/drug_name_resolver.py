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
            # e.g. "Emzor Paracetamol 500mg" → try each word → "Paracetamol" found
            # e.g. "Amoxil 250mg" → skip "250mg" (numeric) → try "Amoxil" → found
            # This handles brands RxNorm doesn't know by extracting the INN.
            # No hardcoding — works for any brand following this naming convention.
            if not result and len(name_lower.split()) > 1:
                import re
                # Extract meaningful words:
                # - 4+ alphabetic characters only
                # - Skip dose strings like "250mg", "400mg", "DS", "XR", "XL"
                # - Skip manufacturer prefixes that are clearly not drug names
                SKIP_WORDS = {
                    'tablet', 'capsule', 'syrup', 'injection', 'suspension',
                    'cream', 'ointment', 'drops', 'plus', 'extra', 'forte',
                    'junior', 'adult', 'night', 'rapid', 'extended', 'release',
                }
                words = re.findall(r'[a-zA-Z]{4,}', drug_name)
                for word in words:
                    word_lower = word.lower()
                    if word_lower == name_lower:
                        continue  # Skip if same as full name
                    if word_lower in SKIP_WORDS:
                        continue  # Skip non-drug descriptor words
                    word_result = await rxnorm_lookup(word)
                    if word_result:
                        result = word_result
                        logger.info(
                            "rxnorm_word_extraction",
                            original=drug_name,
                            matched_word=word,
                            generic=word_result[1],
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
        logger.warning("rxnorm_lookup_failed", drug=drug_name, error=str(error))

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