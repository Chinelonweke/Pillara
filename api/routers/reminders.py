# api/routers/reminders.py

from fastapi import APIRouter, Query, Request

from api.dependencies import CurrentUser, DBSession, VerifiedUser
from schemas.all_schemas import ReminderCreate, ReminderResponse, SuccessResponse
from services.reminder_service import ReminderService
from monitoring.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/", response_model=list[ReminderResponse], summary="List reminders for a profile")
async def list_reminders(
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    profile_id: str = Query(...),
) -> list[ReminderResponse]:
    service = ReminderService(db=db)
    reminders = await service.list_reminders(profile_id=profile_id, user_id=current_user.id)
    return [ReminderResponse.model_validate(r) for r in reminders]


@router.post("/", response_model=ReminderResponse, status_code=201, summary="Create a reminder")
async def create_reminder(
    body: ReminderCreate,
    request: Request,
    current_user: VerifiedUser,
    db: DBSession,
    profile_id: str = Query(...),
) -> ReminderResponse:
    service = ReminderService(db=db)
    reminder = await service.create_reminder(
        profile_id=profile_id,
        user_id=current_user.id,
        reminder_data=body,
        request_id=request.state.request_id,
    )
    return ReminderResponse.model_validate(reminder)


@router.delete("/{reminder_id}", response_model=SuccessResponse, summary="Delete a reminder")
async def delete_reminder(
    reminder_id: str,
    request: Request,
    current_user: VerifiedUser,
    db: DBSession,
) -> SuccessResponse:
    service = ReminderService(db=db)
    await service.delete_reminder(
        reminder_id=reminder_id,
        user_id=current_user.id,
        request_id=request.state.request_id,
    )
    return SuccessResponse(message="Reminder deleted.")