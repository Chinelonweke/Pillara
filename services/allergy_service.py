# services/allergy_service.py
#
# WHY DETERMINISTIC (not LLM-based):
# Drug-class allergy cross-reactivity for well-known classes is not a
# probabilistic judgment — it's established, documented medical fact.
# "Amoxicillin is a penicillin-class antibiotic" is not something that
# needs LLM reasoning; it's a lookup. Running known cross-reactivity
# through an LLM introduces unnecessary uncertainty into a safety-critical
# check that has a correct, deterministic answer.
#
# The LLM/RAG pipeline is the right tool for drug-drug interaction
# checking, where severity genuinely varies by patient context and
# combinations can be nuanced. Allergy cross-reactivity for documented
# classes is different: it's always high-severity, always requires
# clinical review, and should never be downplayed by a model that
# retrieves slightly different context on a different run.
#
# WHY THIS FILE (not inline in the router):
# Allergy checking will eventually be called from multiple places —
# the interaction check endpoint, medication add endpoint (future),
# AI chat context (future). Centralizing the logic here means a single
# audit, a single update when new drug classes are added, and no
# duplicated rule maintenance across files.
#
# LIMITATION / KNOWN GAP:
# This mapping covers major, well-documented drug classes. It does NOT
# cover every possible allergy cross-reactivity — drug allergy medicine
# is genuinely complex, and exhaustive coverage requires integration
# with a clinical drug database (RxNorm, DrugBank, etc.), which is the
# right long-term path. This deterministic layer catches the clear,
# high-confidence cases reliably. The AI/RAG layer handles nuance.
# Together they're stronger than either alone.

from typing import Optional
from schemas.all_schemas import AllergyWarning
from monitoring.logger import get_logger

logger = get_logger(__name__)

# ─── DRUG CLASS MEMBERSHIP MAP ─────────────────────────────────────────────────
# Maps drug names (lowercase) to the allergy class they belong to.
# When a patient has a documented allergy to a class, any drug in that
# class in this map triggers a high-severity warning.
#
# Sources: standard pharmacology references (FDA drug labels, clinical
# pharmacology textbooks). These are well-established, not edge cases.
#
# TO EXTEND: add new entries here. Key = lowercase drug name,
# value = the allergy class string (must match a key in ALLERGY_CLASSES below).

DRUG_TO_CLASS: dict[str, list[str]] = {
    # ── Penicillins ────────────────────────────────────────────────────────────
    "amoxicillin":          ["penicillin", "beta-lactam"],
    "ampicillin":           ["penicillin", "beta-lactam"],
    "penicillin":           ["penicillin", "beta-lactam"],
    "penicillin v":         ["penicillin", "beta-lactam"],
    "penicillin g":         ["penicillin", "beta-lactam"],
    "dicloxacillin":        ["penicillin", "beta-lactam"],
    "nafcillin":            ["penicillin", "beta-lactam"],
    "oxacillin":            ["penicillin", "beta-lactam"],
    "piperacillin":         ["penicillin", "beta-lactam"],
    "amoxicillin-clavulanate": ["penicillin", "beta-lactam"],
    "augmentin":            ["penicillin", "beta-lactam"],

    # ── Cephalosporins (cross-reactivity with penicillin ~1-2%) ───────────────
    "cephalexin":           ["cephalosporin", "beta-lactam"],
    "cefazolin":            ["cephalosporin", "beta-lactam"],
    "cefdinir":             ["cephalosporin", "beta-lactam"],
    "cefuroxime":           ["cephalosporin", "beta-lactam"],
    "ceftriaxone":          ["cephalosporin", "beta-lactam"],
    "cefepime":             ["cephalosporin", "beta-lactam"],
    "cefprozil":            ["cephalosporin", "beta-lactam"],

    # ── Carbapenems (beta-lactam, lower cross-reactivity with penicillin) ─────
    "imipenem":             ["carbapenem", "beta-lactam"],
    "meropenem":            ["carbapenem", "beta-lactam"],
    "ertapenem":            ["carbapenem", "beta-lactam"],
    "doripenem":            ["carbapenem", "beta-lactam"],

    # ── Sulfonamides ──────────────────────────────────────────────────────────
    "sulfamethoxazole":     ["sulfonamide"],
    "trimethoprim-sulfamethoxazole": ["sulfonamide"],
    "bactrim":              ["sulfonamide"],
    "septra":               ["sulfonamide"],
    "sulfadiazine":         ["sulfonamide"],
    "dapsone":              ["sulfonamide"],
    "furosemide":           ["sulfonamide"],       # sulfa-based diuretic
    "hydrochlorothiazide":  ["sulfonamide"],       # sulfa-based diuretic
    "celecoxib":            ["sulfonamide"],       # sulfa-based COX-2 inhibitor

    # ── NSAIDs ────────────────────────────────────────────────────────────────
    "ibuprofen":            ["nsaid"],
    "naproxen":             ["nsaid"],
    "aspirin":              ["nsaid", "salicylate"],
    "celecoxib":            ["nsaid", "sulfonamide"],
    "indomethacin":         ["nsaid"],
    "ketorolac":            ["nsaid"],
    "meloxicam":            ["nsaid"],
    "diclofenac":           ["nsaid"],

    # ── Statins ───────────────────────────────────────────────────────────────
    "atorvastatin":         ["statin"],
    "simvastatin":          ["statin"],
    "rosuvastatin":         ["statin"],
    "pravastatin":          ["statin"],
    "lovastatin":           ["statin"],
    "fluvastatin":          ["statin"],

    # ── ACE Inhibitors ────────────────────────────────────────────────────────
    "lisinopril":           ["ace inhibitor"],
    "enalapril":            ["ace inhibitor"],
    "ramipril":             ["ace inhibitor"],
    "captopril":            ["ace inhibitor"],
    "benazepril":           ["ace inhibitor"],

    # ── Opioids ───────────────────────────────────────────────────────────────
    "morphine":             ["opioid"],
    "codeine":              ["opioid"],
    "oxycodone":            ["opioid"],
    "hydrocodone":          ["opioid"],
    "tramadol":             ["opioid"],
    "fentanyl":             ["opioid"],
    "hydromorphone":        ["opioid"],

    # ── Fluoroquinolones ──────────────────────────────────────────────────────
    "ciprofloxacin":        ["fluoroquinolone"],
    "levofloxacin":         ["fluoroquinolone"],
    "moxifloxacin":         ["fluoroquinolone"],
    "ofloxacin":            ["fluoroquinolone"],

    # ── Macrolides ────────────────────────────────────────────────────────────
    "azithromycin":         ["macrolide"],
    "clarithromycin":       ["macrolide"],
    "erythromycin":         ["macrolide"],

    # ── Tetracyclines ─────────────────────────────────────────────────────────
    "doxycycline":          ["tetracycline"],
    "minocycline":          ["tetracycline"],
    "tetracycline":         ["tetracycline"],
}

# ─── ALLERGY CLASS CROSS-REACTIVITY MAP ────────────────────────────────────────
# Maps patient allergy strings (normalized to lowercase) to the drug classes
# that are known to cross-react with that allergy. Multiple allergen strings
# can map to the same class to handle the ways patients or doctors might
# document the same allergy.
#
# Keys: how the allergy might appear in profile.known_allergies (case-insensitive)
# Values: list of drug class strings (must match values in DRUG_TO_CLASS above)

ALLERGY_CLASS_MAP: dict[str, list[str]] = {
    # Penicillin allergy cross-reacts with all penicillins and cephalosporins
    # (lower risk but clinically relevant) and carbapenems (lower still)
    "penicillin":           ["penicillin", "cephalosporin", "carbapenem", "beta-lactam"],
    "penicillins":          ["penicillin", "cephalosporin", "carbapenem", "beta-lactam"],
    "amoxicillin":          ["penicillin", "cephalosporin", "carbapenem", "beta-lactam"],
    "ampicillin":           ["penicillin", "cephalosporin", "carbapenem", "beta-lactam"],
    "beta-lactam":          ["penicillin", "cephalosporin", "carbapenem", "beta-lactam"],
    "beta lactam":          ["penicillin", "cephalosporin", "carbapenem", "beta-lactam"],

    # Sulfa/sulfonamide allergy
    "sulfa":                ["sulfonamide"],
    "sulfonamide":          ["sulfonamide"],
    "sulfonamides":         ["sulfonamide"],
    "sulfamethoxazole":     ["sulfonamide"],
    "bactrim":              ["sulfonamide"],

    # NSAID allergy (aspirin-exacerbated respiratory disease etc.)
    "nsaid":                ["nsaid"],
    "nsaids":               ["nsaid"],
    "ibuprofen":            ["nsaid"],
    "aspirin":              ["nsaid", "salicylate"],
    "salicylate":           ["nsaid", "salicylate"],
    "naproxen":             ["nsaid"],

    # Statin allergy / intolerance
    "statin":               ["statin"],
    "statins":              ["statin"],
    "atorvastatin":         ["statin"],
    "simvastatin":          ["statin"],

    # ACE inhibitor allergy (common: cough, angioedema)
    "ace inhibitor":        ["ace inhibitor"],
    "ace inhibitors":       ["ace inhibitor"],
    "lisinopril":           ["ace inhibitor"],

    # Opioid allergy
    "opioid":               ["opioid"],
    "opioids":              ["opioid"],
    "morphine":             ["opioid"],
    "codeine":              ["opioid"],

    # Fluoroquinolone allergy
    "fluoroquinolone":      ["fluoroquinolone"],
    "fluoroquinolones":     ["fluoroquinolone"],
    "ciprofloxacin":        ["fluoroquinolone"],
    "quinolone":            ["fluoroquinolone"],

    # Macrolide allergy
    "macrolide":            ["macrolide"],
    "macrolides":           ["macrolide"],
    "azithromycin":         ["macrolide"],
    "erythromycin":         ["macrolide"],
}

# ─── HUMAN-READABLE DESCRIPTIONS ───────────────────────────────────────────────
# Used to generate plain-language warning messages for each cross-reactivity type.

CROSS_REACTIVITY_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "penicillin": {
        "penicillin": (
            "This drug belongs to the penicillin family. You have a documented "
            "Penicillin allergy. Taking this drug carries a high risk of allergic "
            "reaction, which can range from rash to severe anaphylaxis."
        ),
        "cephalosporin": (
            "This drug is a cephalosporin antibiotic. Patients with Penicillin "
            "allergy have approximately 1-2% cross-reactivity with cephalosporins. "
            "Clinical review is required before use."
        ),
        "carbapenem": (
            "This drug is a carbapenem antibiotic. Patients with Penicillin allergy "
            "have a small but real cross-reactivity risk with carbapenems. "
            "Clinical review is required before use."
        ),
        "beta-lactam": (
            "This drug belongs to the beta-lactam class of antibiotics. "
            "You have a documented Penicillin allergy, which is a beta-lactam allergy. "
            "Clinical review is required before use."
        ),
    },
    "sulfonamide": {
        "sulfonamide": (
            "This drug contains a sulfonamide (sulfa) structure. You have a "
            "documented sulfa allergy. Allergic reactions can range from mild "
            "rash to severe Stevens-Johnson syndrome. Do not take without "
            "explicit medical approval."
        ),
    },
    "nsaid": {
        "nsaid": (
            "This drug is an NSAID (non-steroidal anti-inflammatory drug). "
            "You have a documented NSAID or aspirin allergy. NSAIDs share "
            "cross-reactivity, and taking one you haven't tried before carries "
            "real risk. Do not take without clinical review."
        ),
    },
    "statin": {
        "statin": (
            "This drug belongs to the statin (HMG-CoA reductase inhibitor) class. "
            "You have a documented statin allergy or intolerance. Statin allergy "
            "can be class-wide. Clinical review is required before starting "
            "a new statin."
        ),
    },
    "ace inhibitor": {
        "ace inhibitor": (
            "This drug is an ACE inhibitor. You have a documented ACE inhibitor "
            "allergy. A common serious reaction is angioedema (throat swelling), "
            "which is a medical emergency. Do not take without explicit medical "
            "approval."
        ),
    },
    "opioid": {
        "opioid": (
            "This drug is an opioid analgesic. You have a documented opioid "
            "allergy. While true opioid allergy is less common than opioid "
            "intolerance, both require clinical review before prescribing a "
            "different opioid."
        ),
    },
    "fluoroquinolone": {
        "fluoroquinolone": (
            "This drug is a fluoroquinolone antibiotic. You have a documented "
            "fluoroquinolone allergy. Cross-reactivity within this class is "
            "well-established. Do not take without clinical review."
        ),
    },
    "macrolide": {
        "macrolide": (
            "This drug is a macrolide antibiotic. You have a documented macrolide "
            "allergy. Cross-reactivity within this class is possible. "
            "Clinical review is required before use."
        ),
    },
}

ACTION_REQUIRED = (
    "Do not take this medication without first consulting your prescribing doctor "
    "or a pharmacist. Share your allergy history with them directly."
)


async def check_allergies(
    drug_names: list[str],
    known_allergies_str: Optional[str],
    redis=None,
    request_id: str = "unknown",
) -> list[AllergyWarning]:
    """
    Checks a list of drug names against a patient's documented allergies.
    Returns AllergyWarning objects for any known cross-reactivity found.

    THREE-LAYER LOOKUP (in order, fastest to most authoritative):
    Layer 1: Local deterministic map (DRUG_TO_CLASS) — zero latency,
             covers 60+ high-frequency drugs, always runs first.
    Layer 2: RxNorm API — authoritative drug→class taxonomy for ALL
             FDA-approved drugs. Runs only when Layer 1 misses.
    Layer 3: MedRT via RxClass — explicit allergy cross-sensitivity data,
             highest clinical accuracy. Runs alongside Layer 2.
    Layers 2+3 results are cached in Redis permanently — each drug is
    looked up via network exactly once per Redis lifetime.

    Never raises — logs on unexpected error and returns empty list.
    Caller receives a complete, typed result regardless of internal state.

    Args:
        drug_names: list of drug name strings to check
        known_allergies_str: raw string from profile.known_allergies
                             (e.g. "Penicillin, Sulfa") — comma-separated
        redis: Redis client for Layer 2/3 caching (optional — if None,
               Layer 2/3 fallback is skipped, Layer 1 still runs fully)
        request_id: for structured log correlation

    Returns:
        list[AllergyWarning] — empty if no warnings found. Never None.
    """
    warnings: list[AllergyWarning] = []

    if not known_allergies_str or not known_allergies_str.strip():
        return warnings

    if not drug_names:
        return warnings

    try:
        # Parse the comma-separated allergy string into individual allergen tokens
        raw_allergens = [a.strip().lower() for a in known_allergies_str.split(",") if a.strip()]

        # Determine which drug classes the patient is allergic to
        allergic_to_classes: set[str] = set()
        matched_allergens: dict[str, str] = {}  # class -> original allergen string

        for allergen in raw_allergens:
            if allergen in ALLERGY_CLASS_MAP:
                for drug_class in ALLERGY_CLASS_MAP[allergen]:
                    allergic_to_classes.add(drug_class)
                    matched_allergens[drug_class] = allergen

        if not allergic_to_classes:
            logger.info(
                "allergy_check_no_class_match",
                allergens=raw_allergens,
                request_id=request_id,
            )
            return warnings

        # Check each drug against the patient's allergic classes
        for drug_name in drug_names:
            normalized = drug_name.strip().lower()

            # ── Layer 1: Local deterministic map ───────────────────────────────
            drug_classes = DRUG_TO_CLASS.get(normalized, [])

            if not drug_classes:
                # Drug not in local map — log the gap, then try RxNorm/MedRT
                logger.warning(
                    "allergy_check_drug_not_in_class_map",
                    drug_name=drug_name,
                    normalized=normalized,
                    request_id=request_id,
                    note="Falling back to RxNorm/MedRT API lookup.",
                )

                # ── Layer 2+3: RxNorm + MedRT API fallback ─────────────────────
                if redis is not None:
                    from services.drug_taxonomy_service import get_drug_classes
                    api_classes = await get_drug_classes(
                        drug_name=normalized,
                        redis=redis,
                        request_id=request_id,
                    )
                    if api_classes:
                        # Normalize API class names for comparison against
                        # our ALLERGY_CLASS_MAP keys (which are lowercase)
                        drug_classes = [c.lower() for c in api_classes]
                        logger.info(
                            "allergy_check_rxnorm_classes_found",
                            drug_name=drug_name,
                            class_count=len(drug_classes),
                            request_id=request_id,
                        )
                    else:
                        # Both local map and RxNorm/MedRT have no data
                        # for this drug. Log at WARNING — this is a genuine
                        # coverage gap that needs monitoring attention.
                        logger.warning(
                            "allergy_check_no_class_data_any_source",
                            drug_name=drug_name,
                            request_id=request_id,
                            note="Drug not found in local map OR RxNorm/MedRT. "
                                 "Allergy cross-check skipped for this drug. "
                                 "FDA/RAG pipeline still runs independently.",
                        )
                        continue
                else:
                    # No Redis client — skip Layer 2/3, log clearly
                    logger.warning(
                        "allergy_check_no_redis_skip_api_fallback",
                        drug_name=drug_name,
                        request_id=request_id,
                        note="Redis not available, skipping RxNorm/MedRT fallback.",
                    )
                    continue

            for drug_class in drug_classes:
                if drug_class in allergic_to_classes:
                    # Found a cross-reactivity — generate a warning
                    original_allergen = matched_allergens.get(drug_class, drug_class)

                    # Get the right description for this specific cross-reactivity
                    # First try to find a description specific to the patient's
                    # documented allergy → this drug's class
                    description = None
                    allergen_descriptions = CROSS_REACTIVITY_DESCRIPTIONS.get(drug_class, {})

                    # Try to find description for the original allergen type
                    for allergen_token in raw_allergens:
                        if allergen_token in allergen_descriptions:
                            description = allergen_descriptions[allergen_token]
                            break

                    # Fall back to generic drug_class description
                    if not description:
                        description = allergen_descriptions.get(
                            drug_class,
                            f"This drug belongs to the {drug_class} class, "
                            f"which may cross-react with your documented "
                            f"{original_allergen} allergy. Clinical review required."
                        )

                    warning = AllergyWarning(
                        drug_name=drug_name,
                        allergen=original_allergen,
                        severity="high",
                        description=description,
                        action_required=ACTION_REQUIRED,
                    )
                    warnings.append(warning)

                    logger.warning(
                        "allergy_cross_reactivity_detected",
                        drug_name=drug_name,
                        drug_class=drug_class,
                        allergen=original_allergen,
                        request_id=request_id,
                    )

                    # Break after first match per drug per class —
                    # one warning per drug is enough, don't double-warn
                    # for the same drug matching both "penicillin" and "beta-lactam"
                    break

    except Exception as error:
        # WHY LOG-AND-RETURN rather than raise:
        # A bug in allergy checking should never silently eat itself OR
        # crash the entire interaction check. We log loudly (ERROR level,
        # will surface in Sentry once wired) and return empty — the caller
        # still gets a complete response, the LLM/RAG pipeline still runs,
        # and the error is visible and traceable via request_id.
        #
        # This is NOT the same as silent failure — this logs at ERROR
        # level with full context. The distinction: silent failure means
        # nothing is recorded and no one knows. This means the error is
        # fully visible to the engineering team while the user experience
        # degrades gracefully rather than crashing.
        logger.error(
            "allergy_check_error",
            error=str(error),
            error_type=type(error).__name__,
            drug_names=drug_names,
            request_id=request_id,
        )

    return warnings