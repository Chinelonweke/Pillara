# api/routers/reports.py

from fastapi import APIRouter, Query, Request

from api.dependencies import CurrentUser, DBSession, VerifiedUser
from schemas.all_schemas import ReportGenerateRequest, ReportResponse, SuccessResponse
from monitoring.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/generate", response_model=ReportResponse, summary="Generate a medication report PDF")
async def generate_report(
    body: ReportGenerateRequest,
    request: Request,
    current_user: VerifiedUser,
    db: DBSession,
) -> ReportResponse:
    """
    Generates a PDF medication report for a profile.
    IDOR: profile_id is verified against current_user before generating.
    The report contains PHI — stored in /tmp with UUID filename, expires in 1 hour.
    """
    from services.report_service import ReportService
    service = ReportService(db=db)
    return await service.generate_report(
        profile_id=body.profile_id,
        user_id=current_user.id,
        include_inactive=body.include_inactive,
        request_id=request.state.request_id,
    )