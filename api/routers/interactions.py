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
    Checks for interactions between two or more drugs.

    SAFETY DESIGN:
    - Minimum 2 drugs, maximum 10 drugs per request
    - Confidence gate: if retrieved data score < 0.75, returns safe fallback
    - Never guesses on drug interactions — says "I don't have verified data"
    - Audit logged every call (HIPAA: track all PHI access)

    IDOR: profile_id (optional) is verified against current_user before fetching
    profile medications. Foreign profile_id returns empty context, not an error —
    no information leakage about other users' profiles.
    """
    from ai.rag.pipeline import RAGPipeline
    from ai.llm.prompts import build_interaction_prompt
    from ai.llm.client import LLMClient, QueryComplexity
    from monitoring.audit import AuditEventType, AuditLogger, AuditOutcome
    from core.security import sanitize_medication_name, strip_llm_output_html

    audit = AuditLogger(db=db)

    # Sanitize all drug names
    sanitized_drugs = [sanitize_medication_name(name) for name in body.drug_names]
    sanitized_drugs = [d for d in sanitized_drugs if d]  # remove empty strings

    # If profile_id provided, add profile's current medications to the check
    all_drugs = list(sanitized_drugs)
    if body.profile_id:
        try:
            from services.medication_service import MedicationService
            med_service = MedicationService(db=db)
            medications = await med_service.list_medications(
                profile_id=body.profile_id,
                user_id=current_user.id,
                request_id=request.state.request_id,
            )
            profile_drug_names = [m.generic_name or m.name for m in medications if m.is_active]
            # Add profile drugs that aren't already in the check list
            for drug in profile_drug_names:
                if drug.lower() not in [d.lower() for d in all_drugs]:
                    all_drugs.append(drug)
        except Exception:
            pass  # IDOR: silently ignore invalid profile_id

    # Run RAG pipeline for interaction data
    pipeline = RAGPipeline(redis=redis)
    interaction_query = f"drug interactions between {' and '.join(all_drugs)}"

    result = await pipeline.query(
        user_query=interaction_query,
        request_id=request.state.request_id,
    )

    await audit.log(
        event_type=AuditEventType.INTERACTION_CHECKED,
        outcome=AuditOutcome.SUCCESS,
        user_id=current_user.id,
        profile_id=body.profile_id,
        request_id=request.state.request_id,
        details={
            "drug_count": len(all_drugs),
            "confidence_gate_passed": result.confidence_gate_passed,
            "provider": result.provider_used,
        },
    )

    # Determine overall risk from the response
    response_lower = result.response_text.lower()
    if "high" in response_lower and ("risk" in response_lower or "avoid" in response_lower):
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
        overall_risk=overall_risk,
        summary=result.response_text,
        disclaimer=result.disclaimer,
        confidence_gate_passed=result.confidence_gate_passed,
        provider_used=result.provider_used,
        latency_ms=result.latency_ms,
    )