# api/routers/medications.py
#
# MEDICATION ENDPOINTS:
# GET    /medications/              — list medications for a profile
# POST   /medications/              — add a medication
# GET    /medications/{id}          — get one medication (IDOR protected)
# PATCH  /medications/{id}          — update a medication (IDOR protected)
# DELETE /medications/{id}          — soft-delete a medication (IDOR protected)

from fastapi import APIRouter, Query, Request

from api.dependencies import CurrentUser, DBSession, RedisClient, VerifiedUser
from services.medication_service import MedicationService
from schemas.all_schemas import (
    MedicationCreate,
    MedicationResponse,
    MedicationUpdate,
    SuccessResponse,
)
from monitoring.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get(
    "/",
    response_model=list[MedicationResponse],
    summary="List all medications for a profile",
)
async def list_medications(
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    profile_id: str = Query(..., description="Profile ID to list medications for"),
    include_inactive: bool = Query(False, description="Include discontinued medications"),
) -> list[MedicationResponse]:
    """
    IDOR protection: MedicationService.list_medications filters by BOTH
    profile_id AND user_id. A user cannot list another user's medications
    by passing a foreign profile_id.
    """
    service = MedicationService(db=db)
    medications = await service.list_medications(
        profile_id=profile_id,
        user_id=current_user.id,
        include_inactive=include_inactive,
        request_id=request.state.request_id,
    )
    return [MedicationResponse.model_validate(m) for m in medications]


@router.post(
    "/",
    response_model=MedicationResponse,
    status_code=201,
    summary="Add a medication to a profile",
)
async def add_medication(
    medication_data: MedicationCreate,
    request: Request,
    current_user: VerifiedUser,
    db: DBSession,
    profile_id: str = Query(..., description="Profile to add medication to"),
) -> MedicationResponse:
    service = MedicationService(db=db)
    medication = await service.add_medication(
        profile_id=profile_id,
        user_id=current_user.id,
        medication_data=medication_data,
        request_id=request.state.request_id,
    )
    return MedicationResponse.model_validate(medication)


@router.get(
    "/{medication_id}",
    response_model=MedicationResponse,
    summary="Get a specific medication",
)
async def get_medication(
    medication_id: str,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
) -> MedicationResponse:
    """
    IDOR protection: service fetches by medication_id AND verifies
    the medication's profile belongs to current_user.
    Returns 404 if not found OR if it belongs to another user.
    """
    service = MedicationService(db=db)
    medication = await service.get_medication(
        medication_id=medication_id,
        user_id=current_user.id,
        request_id=request.state.request_id,
    )
    return MedicationResponse.model_validate(medication)


@router.patch(
    "/{medication_id}",
    response_model=MedicationResponse,
    summary="Update a medication",
)
async def update_medication(
    medication_id: str,
    update_data: MedicationUpdate,
    request: Request,
    current_user: VerifiedUser,
    db: DBSession,
) -> MedicationResponse:
    """
    MASS ASSIGNMENT PROTECTION: MedicationUpdate schema excludes
    id, profile_id, user_id. Users cannot reassign medication ownership.
    IDOR protection: service validates ownership before updating.
    """
    service = MedicationService(db=db)
    medication = await service.update_medication(
        medication_id=medication_id,
        user_id=current_user.id,
        update_data=update_data,
        request_id=request.state.request_id,
    )
    return MedicationResponse.model_validate(medication)


@router.delete(
    "/{medication_id}",
    response_model=SuccessResponse,
    summary="Remove a medication",
)
async def delete_medication(
    medication_id: str,
    request: Request,
    current_user: VerifiedUser,
    db: DBSession,
) -> SuccessResponse:
    """
    Soft-delete: sets is_active=False. Record is retained for audit history.
    IDOR protection: service validates ownership before deleting.
    """
    service = MedicationService(db=db)
    await service.delete_medication(
        medication_id=medication_id,
        user_id=current_user.id,
        request_id=request.state.request_id,
    )
    return SuccessResponse(message="Medication removed from your list.")