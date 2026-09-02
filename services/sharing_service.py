# services/sharing_service.py

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import AuthorizationError, ProfileNotFoundError, ValidationError
from models.user import Profile, ProfileAccess
from monitoring.audit import AuditEventType, AuditLogger, AuditOutcome
from monitoring.logger import get_logger
from schemas.sharing_schemas import InviteCreateRequest

logger = get_logger(__name__)

INVITE_TOKEN_TTL_DAYS = 7
CLAIM_TOKEN_TTL_DAYS = 7


def _generate_token() -> str:
    return secrets.token_hex(32)


class SharingService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditLogger(db=db)

    async def get_user_role_for_profile(self, profile_id: str, user_id: str) -> str | None:
        result = await self.db.execute(select(Profile).where(Profile.id == profile_id))
        profile = result.scalar_one_or_none()

        if not profile:
            return None

        # Creator of unclaimed profile = owner
        if profile.user_id == user_id and profile.status == "unclaimed":
            return "owner"

        # Owner (patient who claimed ownership)
        if profile.owner_user_id == user_id:
            return "owner"

        # Creator of active profile with no owner assigned yet = owner
        # This happens when a patient creates their own profile directly
        # (owner_user_id is NULL until a claim flow completes)
        if profile.user_id == user_id and profile.owner_user_id is None:
            return "owner"

        # Creator of active profile where someone else has claimed ownership = caregiver
        # This happens when a nurse/caregiver created the profile and the
        # patient later claimed it
        if profile.user_id == user_id and profile.status == "active" and profile.owner_user_id is not None and profile.owner_user_id != user_id:
            return "caregiver"

        # Check explicit access grants
        access_result = await self.db.execute(
            select(ProfileAccess).where(
                and_(
                    ProfileAccess.profile_id == profile_id,
                    ProfileAccess.granted_to_user_id == user_id,
                    ProfileAccess.status == "active",
                )
            )
        )
        access = access_result.scalar_one_or_none()
        if access:
            return access.role

        return None

    async def require_role(self, profile_id: str, user_id: str, minimum_role: str, request_id: str = "unknown") -> str:
        role_hierarchy = {"owner": 3, "caregiver": 2, "viewer": 1}
        actual_role = await self.get_user_role_for_profile(profile_id=profile_id, user_id=user_id)

        if not actual_role:
            raise ProfileNotFoundError(profile_id=profile_id)

        if role_hierarchy.get(actual_role, 0) < role_hierarchy.get(minimum_role, 0):
            raise AuthorizationError(f"This action requires {minimum_role} access. You have {actual_role} access.")

        return actual_role

    async def list_all_accessible_profiles(self, user_id: str) -> list[dict]:
        # Own profiles
        own_result = await self.db.execute(
            select(Profile).where(Profile.user_id == user_id)
            .order_by(Profile.is_primary.desc(), Profile.created_at.asc())
        )
        own_profiles = list(own_result.scalars().all())

        # Profiles shared with this user
        shared_result = await self.db.execute(
            select(Profile).join(
                ProfileAccess,
                and_(
                    ProfileAccess.profile_id == Profile.id,
                    ProfileAccess.granted_to_user_id == user_id,
                    ProfileAccess.status == "active",
                )
            ).where(Profile.user_id != user_id)
        )
        shared_profiles = list(shared_result.scalars().all())

        profiles_with_roles = []

        for profile in own_profiles:
            role = await self.get_user_role_for_profile(profile_id=profile.id, user_id=user_id)
            profiles_with_roles.append({"profile": profile, "role": role, "is_shared_with_me": False})

        for profile in shared_profiles:
            role = await self.get_user_role_for_profile(profile_id=profile.id, user_id=user_id)
            profiles_with_roles.append({"profile": profile, "role": role, "is_shared_with_me": True})

        return profiles_with_roles

    async def create_invite(self, profile_id: str, inviting_user_id: str, invite_data: InviteCreateRequest, request_id: str = "unknown") -> ProfileAccess:
        await self.require_role(profile_id=profile_id, user_id=inviting_user_id, minimum_role="owner", request_id=request_id)

        # Check no duplicate pending/active invite for this email
        existing_result = await self.db.execute(
            select(ProfileAccess).where(
                and_(
                    ProfileAccess.profile_id == profile_id,
                    ProfileAccess.invite_email == invite_data.email.lower(),
                    ProfileAccess.status.in_(["pending", "active"]),
                )
            )
        )
        if existing_result.scalar_one_or_none():
            raise ValidationError("This person already has pending or active access to this profile.")

        invite_token = _generate_token()
        expires_at = datetime.now(tz=timezone.utc) + timedelta(days=INVITE_TOKEN_TTL_DAYS)

        access = ProfileAccess(
            id=str(uuid.uuid4()),
            profile_id=profile_id,
            granted_by_user_id=inviting_user_id,
            granted_to_user_id=None,
            role=invite_data.role,
            invite_token=invite_token,
            invite_token_expires=expires_at,
            invite_email=invite_data.email.lower(),
            status="pending",
        )
        self.db.add(access)
        await self.db.flush()

        await self.audit.log(
            event_type=AuditEventType.PROFILE_INVITE_SENT,
            outcome=AuditOutcome.SUCCESS,
            user_id=inviting_user_id,
            profile_id=profile_id,
            request_id=request_id,
            details={"invite_email": invite_data.email, "role": invite_data.role},
        )
        return access

    async def accept_invite(self, invite_token: str, accepting_user_id: str, accepting_user_email: str, request_id: str = "unknown") -> ProfileAccess:
        result = await self.db.execute(
            select(ProfileAccess).where(
                and_(ProfileAccess.invite_token == invite_token, ProfileAccess.status == "pending")
            )
        )
        access = result.scalar_one_or_none()

        if not access:
            raise ValidationError("Invalid or already used invite link.")

        if access.invite_token_expires < datetime.now(tz=timezone.utc):
            raise ValidationError("This invite link has expired. Ask the profile owner to send a new one.")

        access.granted_to_user_id = accepting_user_id
        access.invite_token = None
        access.invite_token_expires = None
        access.status = "active"

        await self.audit.log(
            event_type=AuditEventType.PROFILE_INVITE_ACCEPTED,
            outcome=AuditOutcome.SUCCESS,
            user_id=accepting_user_id,
            profile_id=access.profile_id,
            request_id=request_id,
            details={"role": access.role},
        )
        return access

    async def revoke_access(self, profile_id: str, target_user_id: str, revoking_user_id: str, request_id: str = "unknown") -> None:
        await self.require_role(profile_id=profile_id, user_id=revoking_user_id, minimum_role="owner", request_id=request_id)

        if target_user_id == revoking_user_id:
            raise ValidationError("You cannot revoke your own access.")

        result = await self.db.execute(
            select(ProfileAccess).where(
                and_(
                    ProfileAccess.profile_id == profile_id,
                    ProfileAccess.granted_to_user_id == target_user_id,
                    ProfileAccess.status == "active",
                )
            )
        )
        access = result.scalar_one_or_none()
        if not access:
            raise ValidationError("This user does not have active access to this profile.")

        access.status = "revoked"
        await self.audit.log(
            event_type=AuditEventType.PROFILE_ACCESS_REVOKED,
            outcome=AuditOutcome.SUCCESS,
            user_id=revoking_user_id,
            profile_id=profile_id,
            request_id=request_id,
            details={"revoked_user_id": target_user_id},
        )

    async def list_members(self, profile_id: str, requesting_user_id: str, request_id: str = "unknown") -> list[ProfileAccess]:
        await self.require_role(profile_id=profile_id, user_id=requesting_user_id, minimum_role="viewer", request_id=request_id)

        result = await self.db.execute(
            select(ProfileAccess).where(
                and_(
                    ProfileAccess.profile_id == profile_id,
                    ProfileAccess.status.in_(["active", "pending"]),
                )
            ).order_by(ProfileAccess.created_at.asc())
        )
        return list(result.scalars().all())

    async def send_claim_invite(self, profile_id: str, patient_email: str, sending_user_id: str, request_id: str = "unknown") -> str:
        result = await self.db.execute(select(Profile).where(Profile.id == profile_id))
        profile = result.scalar_one_or_none()

        if not profile:
            raise ProfileNotFoundError(profile_id=profile_id)
        if profile.user_id != sending_user_id:
            raise AuthorizationError("Only the profile creator can send claim invites.")
        if profile.status == "active" and profile.owner_user_id != sending_user_id:
            raise ValidationError("This profile has already been claimed.")

        claim_token = _generate_token()
        profile.claim_token = claim_token
        profile.claim_token_expires = datetime.now(tz=timezone.utc) + timedelta(days=CLAIM_TOKEN_TTL_DAYS)
        profile.claim_email = patient_email.lower()
        profile.status = "unclaimed"

        return claim_token

    async def claim_profile(self, claim_token: str, claiming_user_id: str, claiming_user_email: str, request_id: str = "unknown") -> Profile:
        result = await self.db.execute(
            select(Profile).where(
                and_(Profile.claim_token == claim_token, Profile.status == "unclaimed")
            )
        )
        profile = result.scalar_one_or_none()

        if not profile:
            raise ValidationError("Invalid or already used claim link.")
        if profile.claim_token_expires < datetime.now(tz=timezone.utc):
            raise ValidationError("This claim link has expired. Ask your caregiver to send a new one.")

        previous_creator_id = profile.user_id
        profile.owner_user_id = claiming_user_id
        profile.status = "active"
        profile.claim_token = None
        profile.claim_token_expires = None

        # Original creator stays as caregiver
        if previous_creator_id != claiming_user_id:
            caregiver_access = ProfileAccess(
                id=str(uuid.uuid4()),
                profile_id=profile.id,
                granted_to_user_id=previous_creator_id,
                granted_by_user_id=claiming_user_id,
                role="caregiver",
                status="active",
            )
            self.db.add(caregiver_access)

        await self.audit.log(
            event_type=AuditEventType.PROFILE_CLAIMED,
            outcome=AuditOutcome.SUCCESS,
            user_id=claiming_user_id,
            profile_id=profile.id,
            request_id=request_id,
            details={"previous_creator_id": previous_creator_id},
        )
        return profile