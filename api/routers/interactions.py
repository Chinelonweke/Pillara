# api/routers/interactions.py

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
    """
    Checks for interactions between two or more drugs, AND checks all
    drugs against the patient's documented allergies.

    SAFETY DESIGN:
    - Minimum 2 drugs, maximum 10 drugs per request
    - Allergy check runs FIRST, deterministically, before the LLM —
      known cross-reactivity is not a probabilistic judgment
    - Confidence gate: if retrieved data score < 0.75, returns safe fallback
    - Never guesses on drug interactions — says "I don't have verified data"
    - Audit logged every call (HIPAA: track all PHI access)
    - Nothing fails silently: all errors logged at ERROR level with
      request_id for Sentry/log correlation

    IDOR: profile_id (optional) is verified against current_user before
    fetching profile medications and allergies. Foreign profile_id returns
    empty context, not an error — no information leakage.
    """
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
    sanitized_drugs = [d for d in sanitized_drugs if d]  # remove empty strings

    # ── STEP 1: Resolve profile context ────────────────────────────────────────
    # If profile_id provided, fetch:
    # (a) profile's existing medications (add to drug list for interaction check)
    # (b) profile's known allergies (for deterministic allergy cross-check)
    #
    # WHY SEPARATE IDOR vs REAL ERROR HANDLING:
    # The previous code used `except Exception: pass` for everything —
    # meaning a real database error (transient connection drop, etc.) was
    # silently swallowed exactly the same as a legitimate IDOR attempt.
    # This means a real error during medication or allergy lookup could
    # cause the check to run with incomplete context, with no one knowing.
    #
    # Correct behavior:
    # - IDOR attempt (profile exists but belongs to someone else) →
    #   ProfileNotFoundError → log at INFO, continue with empty context
    # - Real error (DB down, unexpected exception) →
    #   log at ERROR with full context, continue with empty context
    # Both degrade gracefully, but only real errors surface to monitoring.

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

            # Add profile's existing medications to the drug list
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
                # Legitimate IDOR attempt or profile genuinely not found —
                # log at INFO (expected, no action needed), continue without
                # profile context. Do NOT leak whether profile exists.
                logger.info(
                    "interaction_check_profile_not_found",
                    profile_id=body.profile_id,
                    request_id=request_id,
                )
            else:
                # Real error — log at ERROR level so it surfaces in monitoring
                # (Sentry once wired, structured log in the meantime).
                # We continue rather than crash, but this needs to be visible.
                logger.error(
                    "interaction_check_profile_fetch_failed",
                    error=str(profile_error),
                    error_type=type(profile_error).__name__,
                    profile_id=body.profile_id,
                    request_id=request_id,
                )

    # ── STEP 2: Deterministic allergy cross-check ───────────────────────────────
    # Runs BEFORE the LLM pipeline — known cross-reactivity is a factual
    # lookup, not a judgment call. Results are included regardless of
    # whether the LLM/RAG pipeline returns high confidence or not.
    # redis is passed through to enable RxNorm/MedRT fallback for drugs
    # not in the local map — cached permanently in Redis on first lookup.
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

    # ── STEP 3: LLM/RAG pipeline for drug-drug interaction data ────────────────
    pipeline = RAGPipeline(redis=redis)
    interaction_query = f"drug interactions between {' and '.join(all_drugs)}"

    result = await pipeline.query(
        user_query=interaction_query,
        request_id=request_id,
    )

    # ── STEP 4: Audit log ───────────────────────────────────────────────────────
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

    # ── STEP 5: Determine overall risk ─────────────────────────────────────────
    # If any allergy warning exists, overall risk is always at least "high"
    # regardless of what the LLM pipeline returned — a known allergy
    # cross-reactivity is never downgraded by an uncertain LLM response.
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

    return InteractionCheckResponse(
        drugs_checked=all_drugs,
        interactions_found=[],  # Parsed from LLM response in a future iteration
        allergy_warnings=allergy_warnings,
        overall_risk=overall_risk,
        summary=result.response_text,
        disclaimer=result.disclaimer,
        confidence_gate_passed=result.confidence_gate_passed,
        provider_used=result.provider_used,
        latency_ms=result.latency_ms,
    )