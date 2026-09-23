# api/routers/sharing.py
#
# SHARING ENDPOINTS — all at /api/v1/sharing/ prefix:
# GET    /sharing/all                        — all profiles + shared ones (dashboard)
# POST   /sharing/accept-invite              — accept an invite
# POST   /sharing/claim                      — claim profile ownership
# POST   /sharing/{profile_id}/invite        — invite someone
# GET    /sharing/{profile_id}/members       — list members
# DELETE /sharing/{profile_id}/members/{uid} — revoke access
# POST   /sharing/{profile_id}/send-claim-invite — email patient to claim
#
# WHY SEPARATE PREFIX (/api/v1/sharing not /api/v1/profiles):
# Both routers were mounted at /api/v1/profiles which caused FastAPI
# to match /profiles/all against /profiles/{profile_id} before reaching
# the /all route. Giving sharing its own prefix eliminates the conflict
# entirely — clean architecture, no route ordering hacks needed.

from fastapi import APIRouter, Request

from api.dependencies import CurrentUser, DBSession, VerifiedUser
from services.sharing_service import SharingService
from services.email_service import send_profile_invite_email, send_profile_claim_email
from schemas.sharing_schemas import (
    AcceptInviteRequest,
    ClaimProfileRequest,
    InviteCreateRequest,
    InviteResponse,
    ProfileMemberResponse,
    ProfileWithRoleResponse,
    SendClaimInviteRequest,
)
from schemas.all_schemas import SuccessResponse
from core.config import settings
from monitoring.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get(
    "/all",
    response_model=list[ProfileWithRoleResponse],
    summary="List all profiles including ones shared with you",
)
async def list_all_profiles(
    current_user: CurrentUser,
    db: DBSession,
) -> list[ProfileWithRoleResponse]:
    """
    Powers the dashboard profile switcher.
    Returns own profiles + profiles others have shared with you.
    Each profile includes your role (owner/caregiver/viewer).
    """
    service = SharingService(db=db)
    items = await service.list_all_accessible_profiles(user_id=current_user.id)
    return [
        ProfileWithRoleResponse(
            id=item["profile"].id,
            name=item["profile"].name,
            relationship_to_user=item["profile"].relationship_to_user,
            status=item["profile"].status,
            is_primary=item["profile"].is_primary,
            role=item["role"],
            is_shared_with_me=item["is_shared_with_me"],
            created_at=item["profile"].created_at,
            date_of_birth=item["profile"].date_of_birth,
            gender=item["profile"].gender,
            known_allergies=item["profile"].known_allergies,
            medical_conditions=item["profile"].medical_conditions,
        )
        for item in items
    ]


@router.post(
    "/accept-invite",
    response_model=SuccessResponse,
    summary="Accept a profile sharing invite",
)
async def accept_invite(
    body: AcceptInviteRequest,
    request: Request,
    current_user: VerifiedUser,
    db: DBSession,
) -> SuccessResponse:
    service = SharingService(db=db)
    access = await service.accept_invite(
        invite_token=body.invite_token,
        accepting_user_id=current_user.id,
        accepting_user_email=current_user.email,
        request_id=request.state.request_id,
    )
    return SuccessResponse(
        message=f"You now have {access.role} access. This profile appears in your dashboard."
    )


@router.post(
    "/claim",
    response_model=SuccessResponse,
    summary="Claim ownership of a profile created for you",
)
async def claim_profile(
    body: ClaimProfileRequest,
    request: Request,
    current_user: VerifiedUser,
    db: DBSession,
) -> SuccessResponse:
    service = SharingService(db=db)
    profile = await service.claim_profile(
        claim_token=body.claim_token,
        claiming_user_id=current_user.id,
        claiming_user_email=current_user.email,
        request_id=request.state.request_id,
    )
    return SuccessResponse(
        message=f"You are now the owner of '{profile.name}'. It appears in your dashboard."
    )


@router.post(
    "/{profile_id}/invite",
    response_model=InviteResponse,
    status_code=201,
    summary="Invite someone to access a profile",
)
async def invite_member(
    profile_id: str,
    invite_data: InviteCreateRequest,
    request: Request,
    current_user: VerifiedUser,
    db: DBSession,
) -> InviteResponse:
    service = SharingService(db=db)
    access = await service.create_invite(
        profile_id=profile_id,
        inviting_user_id=current_user.id,
        invite_data=invite_data,
        request_id=request.state.request_id,
    )
    invite_link = f"{settings.FRONTEND_URL}/accept-invite?token={access.invite_token}"
    await send_profile_invite_email(
        to_email=invite_data.email,
        invite_link=invite_link,
        role=invite_data.role,
        inviter_name=current_user.email,
    )
    return InviteResponse(
        invite_token=access.invite_token,
        invite_email=access.invite_email,
        role=access.role,
        expires_at=access.invite_token_expires,
        message=f"Invite sent to {invite_data.email}. They have 7 days to accept.",
    )


@router.get(
    "/{profile_id}/members",
    response_model=list[ProfileMemberResponse],
    summary="List all members with access to a profile",
)
async def list_members(
    profile_id: str,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
) -> list[ProfileMemberResponse]:
    service = SharingService(db=db)
    members = await service.list_members(
        profile_id=profile_id,
        requesting_user_id=current_user.id,
        request_id=request.state.request_id,
    )
    return [
        ProfileMemberResponse(
            user_id=m.granted_to_user_id,
            email=m.invite_email,
            role=m.role,
            status=m.status,
            invited_at=m.created_at,
        )
        for m in members
    ]


@router.delete(
    "/{profile_id}/members/{target_user_id}",
    response_model=SuccessResponse,
    summary="Revoke a member's access to a profile",
)
async def revoke_member(
    profile_id: str,
    target_user_id: str,
    request: Request,
    current_user: VerifiedUser,
    db: DBSession,
) -> SuccessResponse:
    service = SharingService(db=db)
    await service.revoke_access(
        profile_id=profile_id,
        target_user_id=target_user_id,
        revoking_user_id=current_user.id,
        request_id=request.state.request_id,
    )
    return SuccessResponse(message="Access revoked successfully.")


@router.post(
    "/{profile_id}/send-claim-invite",
    response_model=SuccessResponse,
    summary="Email the patient to claim their profile",
)
async def send_claim_invite(
    profile_id: str,
    body: SendClaimInviteRequest,
    request: Request,
    current_user: VerifiedUser,
    db: DBSession,
) -> SuccessResponse:
    service = SharingService(db=db)
    claim_token = await service.send_claim_invite(
        profile_id=profile_id,
        patient_email=body.patient_email,
        sending_user_id=current_user.id,
        request_id=request.state.request_id,
    )
    claim_link = f"{settings.FRONTEND_URL}/claim-profile?token={claim_token}"
    await send_profile_claim_email(
        to_email=body.patient_email,
        claim_link=claim_link,
        caregiver_email=current_user.email,
    )
    return SuccessResponse(
        message=f"Claim invitation sent to {body.patient_email}. They have 7 days to claim."
    )