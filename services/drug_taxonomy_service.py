# services/drug_taxonomy_service.py
#
# WHY THIS EXISTS AS A SEPARATE SERVICE:
# Drug class taxonomy (what class does this drug belong to?) and allergy
# cross-sensitivity data (is this class cross-reactive with this allergy?)
# are authoritative, structured data problems — not text retrieval problems.
# This service provides the Layer 2/3 fallback when the local deterministic
# map in allergy_service.py doesn't have a drug. It never replaces the local
# map; it extends it.
#
# DATA SOURCES:
# ┌─────────────────┬──────────────────────────────────────────────────────┐
# │ Source          │ What it answers                                      │
# ├─────────────────┼──────────────────────────────────────────────────────┤
# │ Local map       │ Fast, offline, covers 60+ high-frequency drugs       │
# │ RxNorm/RxClass  │ Authoritative drug→class taxonomy for ALL FDA drugs  │
# │ MedRT           │ Explicit allergy cross-sensitivity (highest accuracy) │
# │ FDA/ChromaDB    │ Unstructured drug text, interactions, contraindic.   │
# └─────────────────┴──────────────────────────────────────────────────────┘
#
# API DETAILS:
# Both RxNorm and MedRT are served by the NLM RxNav API — no API key needed,
# free forever, government-maintained. MedRT data is accessed via the same
# RxClass API using relaSource=MEDRT.
#
# CACHING STRATEGY:
# Drug class membership is stable data — amoxicillin will be a penicillin
# forever. We cache RxNorm results in Redis with no TTL (permanent cache).
# This means each drug is looked up via network exactly once per Redis
# instance lifetime. In production, a Redis flush or a new deployment would
# trigger fresh lookups, which is fine.
#
# FAILURE HANDLING:
# If RxNorm/MedRT is unavailable, this service returns empty lists and logs
# the failure. The caller (allergy_service.py) degrades gracefully — the
# local map already ran, so the most critical cases are already covered.
# Nothing fails silently: all API failures log at WARNING with request_id.

import json
from typing import Optional

import httpx

from core.config import settings
from monitoring.logger import get_logger

logger = get_logger(__name__)

RXNORM_BASE = settings.RXNORM_API_BASE_URL
TIMEOUT = settings.RXNORM_API_TIMEOUT

# Redis cache key prefix for drug class lookups
CACHE_PREFIX = "drug_class:"


async def get_drug_classes(
    drug_name: str,
    redis,
    request_id: str = "unknown",
) -> list[str]:
    """
    Returns the pharmacological class names for a given drug name.

    Lookup order:
    1. Redis cache (permanent, set on first lookup)
    2. RxNorm API → RxClass API (authoritative NLM taxonomy)
    3. MedRT via RxClass (explicit allergy cross-sensitivity data)

    Returns a list of normalized class name strings, or empty list if
    the drug is not found or all APIs are unavailable.

    Never raises — logs and returns empty list on any failure.
    """
    normalized = drug_name.strip().lower()
    cache_key = f"{CACHE_PREFIX}{normalized}"

    # ── Step 1: Check Redis cache ───────────────────────────────────────────────
    try:
        cached = await redis.get(cache_key)
        if cached:
            classes = json.loads(cached)
            logger.info(
                "drug_class_cache_hit",
                drug_name=drug_name,
                class_count=len(classes),
                request_id=request_id,
            )
            return classes
    except Exception as cache_error:
        # Cache miss or Redis error — continue to API lookup
        logger.warning(
            "drug_class_cache_error",
            error=str(cache_error),
            drug_name=drug_name,
            request_id=request_id,
        )

    # ── Step 2: RxNorm lookup — get RxCUI for this drug name ───────────────────
    rxcui = await _get_rxcui(drug_name=normalized, request_id=request_id)

    if not rxcui:
        logger.warning(
            "drug_class_rxcui_not_found",
            drug_name=drug_name,
            request_id=request_id,
            note="Drug not found in RxNorm. May be a brand name, "
                 "misspelling, or a drug not yet in RxNorm vocabulary.",
        )
        return []

    # ── Step 3: RxClass lookup — get pharmacological classes via RxNorm ────────
    rxnorm_classes = await _get_classes_from_rxclass(
        rxcui=rxcui,
        rela_source="NDFRT",   # National Drug File Reference Terminology
        relas="has_PE",        # Physiologic Effect — the right relation for allergy
        request_id=request_id,
    )

    # ── Step 4: MedRT lookup — explicit allergy cross-sensitivity data ─────────
    # MedRT (successor to NDF-RT) is specifically designed for pharmacological
    # properties and is the highest-accuracy source for allergy classification.
    medrt_classes = await _get_classes_from_rxclass(
        rxcui=rxcui,
        rela_source="MEDRT",
        relas="has_PE",        # Physiologic Effect (mechanism relevant to allergy)
        request_id=request_id,
    )

    # Combine and deduplicate — normalize to lowercase for consistent comparison
    all_classes = list({
        c.lower()
        for c in (rxnorm_classes + medrt_classes)
        if c
    })

    if all_classes:
        logger.info(
            "drug_class_resolved",
            drug_name=drug_name,
            rxcui=rxcui,
            class_count=len(all_classes),
            classes=all_classes,
            request_id=request_id,
        )
    else:
        logger.warning(
            "drug_class_no_classes_found",
            drug_name=drug_name,
            rxcui=rxcui,
            request_id=request_id,
            note="RxCUI found but no pharmacological classes returned "
                 "from RxNorm or MedRT. Drug may have unusual classification.",
        )

    # ── Step 5: Cache the result permanently ───────────────────────────────────
    # Drug classes don't change — safe to cache forever.
    # Cache even empty results to avoid repeated API calls for unknown drugs.
    try:
        await redis.set(cache_key, json.dumps(all_classes))
        # No TTL — permanent cache. A Redis flush would clear this,
        # which is fine since the API will repopulate on next lookup.
    except Exception as cache_write_error:
        # Non-fatal: we have the result, just couldn't cache it
        logger.warning(
            "drug_class_cache_write_failed",
            error=str(cache_write_error),
            drug_name=drug_name,
            request_id=request_id,
        )

    return all_classes


async def _get_rxcui(drug_name: str, request_id: str) -> Optional[str]:
    """
    Gets the RxNorm Concept Unique Identifier (RxCUI) for a drug name.
    RxCUI is needed for all subsequent RxClass lookups.

    API: GET /rxcui.json?name={drug_name}&search=1
    search=1 means approximate matching — handles brand names, slight
    spelling variations, and common abbreviations.
    """
    url = f"{RXNORM_BASE}/rxcui.json"
    params = {"name": drug_name, "search": "1"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # RxNorm returns idGroup.rxnormId as a list; take the first
            rxnorm_ids = (
                data.get("idGroup", {}).get("rxnormId", [])
            )
            if rxnorm_ids:
                return rxnorm_ids[0]
            return None

    except httpx.TimeoutException:
        logger.warning(
            "rxnorm_rxcui_timeout",
            drug_name=drug_name,
            url=url,
            timeout_seconds=TIMEOUT,
            request_id=request_id,
        )
        return None

    except httpx.HTTPStatusError as http_error:
        logger.warning(
            "rxnorm_rxcui_http_error",
            drug_name=drug_name,
            status_code=http_error.response.status_code,
            request_id=request_id,
        )
        return None

    except Exception as error:
        logger.error(
            "rxnorm_rxcui_unexpected_error",
            drug_name=drug_name,
            error=str(error),
            error_type=type(error).__name__,
            request_id=request_id,
        )
        return None


async def _get_classes_from_rxclass(
    rxcui: str,
    rela_source: str,
    relas: str,
    request_id: str,
) -> list[str]:
    """
    Gets drug class names from the RxClass API for a given RxCUI.

    Works for both RxNorm (relaSource=NDFRT) and MedRT (relaSource=MEDRT).
    Returns a list of class name strings.

    API: GET /rxclass/class/byRxcui.json?rxcui={rxcui}&relaSource={source}&relas={relas}
    """
    url = f"{RXNORM_BASE}/rxclass/class/byRxcui.json"
    params = {
        "rxcui": rxcui,
        "relaSource": rela_source,
        "relas": relas,
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # Extract class names from the nested response structure
            drug_info_list = (
                data
                .get("rxclassDrugInfoList", {})
                .get("rxclassDrugInfo", [])
            )

            class_names = []
            for entry in drug_info_list:
                class_item = entry.get("rxclassMinConceptItem", {})
                class_name = class_item.get("className", "")
                if class_name:
                    class_names.append(class_name)

            return class_names

    except httpx.TimeoutException:
        logger.warning(
            "rxclass_timeout",
            rxcui=rxcui,
            rela_source=rela_source,
            timeout_seconds=TIMEOUT,
            request_id=request_id,
        )
        return []

    except httpx.HTTPStatusError as http_error:
        logger.warning(
            "rxclass_http_error",
            rxcui=rxcui,
            rela_source=rela_source,
            status_code=http_error.response.status_code,
            request_id=request_id,
        )
        return []

    except Exception as error:
        logger.error(
            "rxclass_unexpected_error",
            rxcui=rxcui,
            rela_source=rela_source,
            error=str(error),
            error_type=type(error).__name__,
            request_id=request_id,
        )
        return []