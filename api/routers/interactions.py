# api/routers/interactions.py

import json

from fastapi import APIRouter, Depends, Request

from api.dependencies import (
    DBSession, RedisClient, VerifiedUser,
    rate_limit_api, rate_limit_llm,
)
from schemas.all_schemas import InteractionCheckRequest, InteractionCheckResponse
from monitoring.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post(
    "/check",
    response_model=InteractionCheckResponse,
    summary="Check drug interactions",
    dependencies=[Depends(rate_limit_api), Depends(rate_limit_llm)],
)
async def check_interactions(
    body: InteractionCheckRequest,
    request: Request,
    current_user: VerifiedUser,
    db: DBSession,
    redis: RedisClient,
) -> InteractionCheckResponse:
    from ai.rag.pipeline import RAGPipeline
    from monitoring.audit import AuditEventType, AuditLogger, AuditOutcome
    from core.security import sanitize_medication_name
    from services.allergy_service import check_allergies
    from services.medication_service import MedicationService
    from services.profile_service import ProfileService

    audit = AuditLogger(db=db)
    request_id = request.state.request_id

    # Sanitize all drug names
    sanitized_drugs = [sanitize_medication_name(name) for name in body.drug_names]
    sanitized_drugs = [d for d in sanitized_drugs if d]

    # ── CACHE CHECK ────────────────────────────────────────────────────────────
    # Identical drug combinations always produce the same interaction result.
    # Sorted key means ["aspirin","ibuprofen"] == ["ibuprofen","aspirin"].
    # Only cache requests without a profile_id — profile-specific requests
    # include patient medications and allergy data which vary per patient.
    cache_key = "interaction:" + ":".join(sorted(d.lower() for d in sanitized_drugs))
    if not body.profile_id:
        try:
            cached = await redis.get(cache_key)
            if cached:
                logger.info("interaction_cache_hit", drugs=sanitized_drugs)
                return InteractionCheckResponse(**json.loads(cached))
        except Exception as cache_error:
            logger.debug("interaction_cache_read_failed", error=str(cache_error))

    # ── STEP 1: Resolve profile context ───────────────────────────────────────
    all_drugs = list(sanitized_drugs)
    known_allergies: str = ""

    if body.profile_id:
        try:
            profile_service = ProfileService(db=db)
            profile = await profile_service.get_profile(
                profile_id=body.profile_id,
                user_id=current_user.id,
                request_id=request_id,
            )
            known_allergies = profile.known_allergies or ""

            med_service = MedicationService(db=db)
            medications = await med_service.list_medications(
                profile_id=body.profile_id,
                user_id=current_user.id,
                request_id=request_id,
            )
            profile_drug_names = [
                m.generic_name or m.name
                for m in medications
                if m.is_active
            ]
            for drug in profile_drug_names:
                if drug.lower() not in [d.lower() for d in all_drugs]:
                    all_drugs.append(drug)

        except Exception as profile_error:
            from core.exceptions import NotFoundError
            if isinstance(profile_error, NotFoundError):
                logger.info(
                    "interaction_check_profile_not_found",
                    profile_id=body.profile_id,
                    request_id=request_id,
                )
            else:
                logger.error(
                    "interaction_check_profile_fetch_failed",
                    error=str(profile_error),
                    error_type=type(profile_error).__name__,
                    profile_id=body.profile_id,
                    request_id=request_id,
                )

    # ── STEP 2: Deterministic allergy cross-check ──────────────────────────────
    allergy_warnings = await check_allergies(
        drug_names=all_drugs,
        known_allergies_str=known_allergies,
        redis=redis,
        request_id=request_id,
    )

    if allergy_warnings:
        logger.warning(
            "interaction_check_allergy_warnings_found",
            warning_count=len(allergy_warnings),
            drugs=all_drugs,
            request_id=request_id,
        )

    # ── STEP 3: openFDA drug label interaction lookup ─────────────────────────
    # openFDA returns the official FDA drug label "drug_interactions" section
    # for each drug — explicit clinical interaction warnings by name.
    # Free, no API key required, maintained by FDA.
    # This gives the LLM verified interaction text to reason from.
    import httpx
    fda_interaction_context = []

    for drug in all_drugs:
        cache_key = f"fda:interactions:{drug.lower()}"
        cached_text = None

        # Check Redis cache first
        if redis:
            try:
                cached = await redis.get(cache_key)
                if cached:
                    cached_text = cached.decode()
            except Exception:
                pass

        if cached_text:
            fda_interaction_context.append(f"{drug.upper()} (FDA label interactions):\n{cached_text}")
            continue

        # Query openFDA drug label API — fail loudly on any error
        async with httpx.AsyncClient(timeout=8.0) as client:
            # Try generic_name first, then brand_name as fallback
            fda_url = "https://api.fda.gov/drug/label.json"
            search_queries = [
                f"openfda.generic_name:{drug}",
                f"openfda.brand_name:{drug}",
                f"openfda.substance_name:{drug}",
            ]
            interactions_text = ""
            for search_q in search_queries:
                r = await client.get(fda_url, params={"search": search_q, "limit": 1})
                logger.info(
                    "fda_label_query",
                    drug=drug,
                    search=search_q,
                    status=r.status_code,
                )
                if r.status_code == 200:
                    results = r.json().get("results", [])
                    if results:
                        interactions_text = results[0].get("drug_interactions", [""])[0]
                        if interactions_text:
                            break  # Found it — stop trying other queries

            if interactions_text:
                # Clean encoding — fix mojibake from double-encoded UTF-8
                # The FDA API sometimes returns text that was encoded twice
                try:
                    # Try to fix mojibake: re-encode as latin-1 then decode as utf-8
                    interactions_text = interactions_text.encode('latin-1').decode('utf-8')
                except (UnicodeDecodeError, UnicodeEncodeError):
                    pass
                # Replace special characters with clean ASCII equivalents
                interactions_text = (
                    interactions_text
                    .replace('—', '-')      # em dash → hyphen
                    .replace('–', '-')      # en dash → hyphen
                    .replace('’', "'")      # right single quote → apostrophe
                    .replace('‘', "'")      # left single quote → apostrophe
                    .replace('“', '"')      # left double quote
                    .replace('”', '"')      # right double quote
                    .replace('®', '')       # registered trademark → remove
                    .replace('±', '+/-')    # plus-minus
                    .replace(' ', ' ')      # non-breaking space → space
                    .replace('•', '-')      # bullet → hyphen
                )
                truncated = interactions_text[:800]
                label = f"{drug.upper()} (FDA label interactions):\n{truncated}"
                fda_interaction_context.append(label)
                logger.info(
                    "fda_interaction_label_fetched",
                    drug=drug,
                    text_length=len(interactions_text),
                )
                # Cache for 24 hours
                if redis:
                    await redis.setex(cache_key, 86400, truncated)
            else:
                logger.warning(
                    "fda_interaction_label_not_found",
                    drug=drug,
                    message="No drug_interactions field found in FDA label",
                )

    # ── STEP 4: LLM/RAG pipeline ───────────────────────────────────────────────
    pipeline = RAGPipeline(redis=redis)
    drug_list = ", ".join(all_drugs)

    if fda_interaction_context:
        # Prepend FDA label data to the query so RAG retrieval is anchored
        fda_context_str = "\n\n".join(fda_interaction_context)
        interaction_query = (
            f"drug interactions safety warnings for {drug_list}.\n\n"
            f"VERIFIED FDA DRUG LABEL INTERACTION DATA:\n{fda_context_str}"
        )
    else:
        interaction_query = f"drug interactions safety warnings for {drug_list}"

    result = await pipeline.query(
        user_query=interaction_query,
        request_id=request_id,
        max_tokens=2048,  # Interaction checks need more tokens — 6 pairs × ~150 tokens each
    )

    from monitoring.analytics import track
    track("interaction_checked", user_id=str(current_user.id), properties={
    "drug_count": len(all_drugs),
    "allergy_warnings": len(allergy_warnings),
    })

    # ── STEP 4: Audit log ──────────────────────────────────────────────────────
    await audit.log(
        event_type=AuditEventType.INTERACTION_CHECKED,
        outcome=AuditOutcome.SUCCESS,
        user_id=current_user.id,
        profile_id=body.profile_id,
        request_id=request_id,
        details={
            "drug_count": len(all_drugs),
            "allergy_warning_count": len(allergy_warnings),
            "confidence_gate_passed": result.confidence_gate_passed,
            "provider": result.provider_used,
        },
    )

    # ── STEP 5: Determine overall risk ────────────────────────────────────────
    # Allergy warnings are deterministic — always highest priority.
    # For LLM risk: extract structured RISK_LEVEL tag from response.
    import re
    if allergy_warnings:
        overall_risk = "high"
    elif not result.confidence_gate_passed:
        overall_risk = "unknown"
    else:
        risk_match = re.search(
            r'RISK_LEVEL:\s*(high|moderate|low|none)',
            result.response_text,
            re.IGNORECASE,
        )
        if risk_match:
            overall_risk = risk_match.group(1).lower()
        else:
            overall_risk = "unknown"
            logger.warning(
                "risk_level_not_found_in_response",
                response_preview=result.response_text[:100],
            )

    # ── STEP 6: Build response and cache ──────────────────────────────────────
    response_data = InteractionCheckResponse(
        drugs_checked=all_drugs,
        interactions_found=[],
        allergy_warnings=allergy_warnings,
        overall_risk=overall_risk,
        summary=result.response_text,
        disclaimer=result.disclaimer,
        confidence_gate_passed=result.confidence_gate_passed,
        provider_used=result.provider_used,
        latency_ms=result.latency_ms,
    )

    # Cache only non-profile requests — profile results include patient-specific data
    if not body.profile_id and not allergy_warnings:
        try:
            await redis.setex(cache_key, 86400, json.dumps(response_data.model_dump()))
        except Exception as cache_write_error:
            logger.warning("interaction_cache_write_failed", error=str(cache_write_error))

    return response_data