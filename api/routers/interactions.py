# api/routers/interactions.py

import json

from fastapi import APIRouter, Depends, Request

from api.dependencies import (
    CurrentUser, DBSession, RedisClient, VerifiedUser,
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
    from ai.llm.prompts import build_interaction_prompt
    from ai.llm.client import LLMClient, QueryComplexity
    from monitoring.audit import AuditEventType, AuditLogger, AuditOutcome
    from core.security import sanitize_medication_name, strip_llm_output_html
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
        except Exception:
            pass  # Cache miss or Redis error — proceed normally

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

    # ── STEP 3: LLM/RAG pipeline ───────────────────────────────────────────────
    pipeline = RAGPipeline(redis=redis)
    interaction_query = f"drug interactions between {' and '.join(all_drugs)}"

    result = await pipeline.query(
        user_query=interaction_query,
        request_id=request_id,
    )

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
    # Allergy warnings always take priority — never downgraded by LLM output
    response_lower = result.response_text.lower()
    if allergy_warnings:
        overall_risk = "high"
    elif "high" in response_lower and ("risk" in response_lower or "avoid" in response_lower):
        overall_risk = "high"
    elif "moderate" in response_lower:
        overall_risk = "moderate"
    elif "low" in response_lower or "minor" in response_lower:
        overall_risk = "low"
    elif not result.confidence_gate_passed:
        overall_risk = "unknown"
    else:
        overall_risk = "none"

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
        except Exception:
            pass

    return response_data