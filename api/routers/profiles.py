# api/routers/profiles.py

# NOTE: Sharing endpoints live at /api/v1/sharing/ — separate prefix
# avoids all route conflicts with /{profile_id}.

from uuid import UUID

from fastapi import APIRouter, Request

from api.dependencies import CurrentUser, DBSession, VerifiedUser
from services.profile_service import ProfileService
from schemas.all_schemas import (
    ProfileCreate,
    ProfileResponse,
    ProfileUpdate,
    SuccessResponse,
)
from monitoring.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get(
    "/",
    response_model=list[ProfileResponse],
    summary="List all profiles for the current user",
)
async def list_profiles(
    current_user: CurrentUser,
    db: DBSession,
) -> list[ProfileResponse]:
    """
    Returns all profiles belonging to the authenticated user.
    IDOR safe: query always filters by current_user.id.
    """
    service = ProfileService(db=db)
    profiles = await service.list_profiles(user_id=current_user.id)
    return [ProfileResponse.model_validate(p) for p in profiles]


@router.post(
    "/",
    response_model=ProfileResponse,
    status_code=201,
    summary="Create a new profile",
)
async def create_profile(
    profile_data: ProfileCreate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
) -> ProfileResponse:
    """
    WHY CurrentUser (not VerifiedUser):
    Profile creation happens during onboarding before email verification.
    The verification gate applies to safety-critical features only.
    """
    service = ProfileService(db=db)
    profile = await service.create_profile(
        user_id=current_user.id,
        profile_data=profile_data,
        request_id=request.state.request_id,
    )
    return ProfileResponse.model_validate(profile)


@router.get(
    "/{profile_id}",
    response_model=ProfileResponse,
    summary="Get a specific profile",
)
async def get_profile(
    profile_id: UUID,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
) -> ProfileResponse:
    """
    WHY profile_id is UUID type:
    FastAPI validates path param as UUID before the route runs.
    Any non-UUID string is rejected at routing level — 422 returned
    immediately, no database query runs.
    IDOR protection: profile_id validated against current_user.id in service.
    """
    service = ProfileService(db=db)
    profile = await service.get_profile(
        profile_id=str(profile_id),
        user_id=current_user.id,
        request_id=request.state.request_id,
    )
    return ProfileResponse.model_validate(profile)


@router.patch(
    "/{profile_id}",
    response_model=ProfileResponse,
    summary="Update a profile",
)
async def update_profile(
    profile_id: UUID,
    update_data: ProfileUpdate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
) -> ProfileResponse:
    """
    MASS ASSIGNMENT PROTECTION: ProfileUpdate schema excludes id, user_id, is_primary.
    IDOR protection: service validates profile belongs to current_user.
    """
    service = ProfileService(db=db)
    profile = await service.update_profile(
        profile_id=str(profile_id),
        user_id=current_user.id,
        update_data=update_data,
        request_id=request.state.request_id,
    )
    return ProfileResponse.model_validate(profile)


@router.delete(
    "/{profile_id}",
    response_model=SuccessResponse,
    summary="Delete a profile",
)
async def delete_profile(
    profile_id: UUID,
    request: Request,
    current_user: VerifiedUser,
    db: DBSession,
) -> SuccessResponse:
    """
    Cannot delete the primary profile.
    IDOR protection: service validates ownership.
    """
    service = ProfileService(db=db)
    await service.delete_profile(
        profile_id=str(profile_id),
        user_id=current_user.id,
        request_id=request.state.request_id,
    )
    return SuccessResponse(message="Profile deleted.")