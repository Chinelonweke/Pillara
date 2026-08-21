# services/allergy_service.py


from typing import Optional
from schemas.all_schemas import AllergyWarning
from monitoring.logger import get_logger

logger = get_logger(__name__)

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
        logger.error(
            "allergy_check_error",
            error=str(error),
            error_type=type(error).__name__,
            drug_names=drug_names,
            request_id=request_id,
        )

    return warnings