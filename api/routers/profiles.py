# api/routers/profiles.py
#
# PROFILE ENDPOINTS:
# GET    /profiles/          — list all profiles for current user
# POST   /profiles/          — create a new profile
# GET    /profiles/{id}      — get one profile (IDOR protected)
# PATCH  /profiles/{id}      — update a profile (IDOR protected)
# DELETE /profiles/{id}      — delete a profile (IDOR protected)
# GET    /profiles/{id}/insights — get AI health insights for profile

from fastapi import APIRouter, Request

from api.dependencies import CurrentUser, DBSession, RedisClient, VerifiedUser, rate_limit_llm
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
    IDOR safe: query always filters by current_user.id — users only see their own profiles.
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
    # WHY CurrentUser (not VerifiedUser) HERE:
    # Profile creation and update are required during onboarding, which
    # happens immediately after registration before the user has had a
    # chance to verify their email. Blocking profile setup behind email
    # verification creates a chicken-and-egg problem: users can't use
    # the app meaningfully until their profile is complete, but they
    # can't complete their profile if email verification is required first.
    # The verification gate is correctly applied to the safety-critical
    # features (interaction checking, AI chat) — not to profile management,
    # which is harmless data the user is entering about themselves.
    db: DBSession,
) -> ProfileResponse:
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
    profile_id: str,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
) -> ProfileResponse:
    """
    IDOR protection: profile_id is validated against current_user.id inside the service.
    A user cannot fetch another user's profile — they get 404.
    """
    service = ProfileService(db=db)
    profile = await service.get_profile(
        profile_id=profile_id,
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
    profile_id: str,
    update_data: ProfileUpdate,
    request: Request,
    current_user: CurrentUser,
    # WHY CurrentUser: same reasoning as create_profile above —
    # profile updates must work during onboarding before email verification.
    db: DBSession,
) -> ProfileResponse:
    """
    MASS ASSIGNMENT PROTECTION: ProfileUpdate schema excludes id, user_id, is_primary.
    Users cannot change profile ownership or promote themselves via field injection.
    IDOR protection: service validates profile belongs to current_user.
    """
    service = ProfileService(db=db)
    profile = await service.update_profile(
        profile_id=profile_id,
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
    profile_id: str,
    request: Request,
    current_user: VerifiedUser,
    db: DBSession,
) -> SuccessResponse:
    """
    Cannot delete the primary profile — at least one profile must always exist.
    IDOR protection: service validates ownership.
    """
    service = ProfileService(db=db)
    await service.delete_profile(
        profile_id=profile_id,
        user_id=current_user.id,
        request_id=request.state.request_id,
    )
    return SuccessResponse(message="Profile deleted.")
