from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ProfileNotFoundError
from models.user import Profile
from monitoring.audit import AuditEventType, AuditLogger, AuditOutcome
from monitoring.logger import get_logger
from schemas.all_schemas import ProfileCreate, ProfileUpdate

logger = get_logger(__name__)


class ProfileService:

    def __init__(self, db: AsyncSession, redis=None):
        self.db = db
        self.audit = AuditLogger(db=db)

    async def list_profiles(self, user_id: str) -> list[Profile]:
        result = await self.db.execute(
            select(Profile)
            .where(Profile.user_id == user_id)
            .order_by(Profile.is_primary.desc(), Profile.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_profile(self, profile_id: str, user_id: str, request_id: str = "unknown") -> Profile:
        """
        Role-aware: allows owners, caregivers, and viewers to fetch a profile.
        Checks all three access routes: user_id, owner_user_id, ProfileAccess.
        """
        from services.sharing_service import SharingService
        sharing = SharingService(db=self.db)
        role = await sharing.get_user_role_for_profile(profile_id=profile_id, user_id=user_id)
        if not role:
            raise ProfileNotFoundError(profile_id=profile_id)
        result = await self.db.execute(
            select(Profile).where(Profile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            raise ProfileNotFoundError(profile_id=profile_id)

        await self.audit.log(
            event_type=AuditEventType.PROFILE_VIEWED,
            outcome=AuditOutcome.SUCCESS,
            user_id=user_id,
            profile_id=profile_id,
            request_id=request_id,
        )
        return profile

    async def create_profile(self, user_id: str, profile_data: ProfileCreate, request_id: str = "unknown") -> Profile:
        from core.security import sanitize_text_input

        profile = Profile(
            user_id=user_id,
            name=sanitize_text_input(profile_data.name, max_length=100),
            relationship_to_user=profile_data.relationship_to_user,
            date_of_birth=(
                profile_data.date_of_birth.replace(tzinfo=__import__('datetime').timezone.utc)
                if profile_data.date_of_birth and profile_data.date_of_birth.tzinfo is None
                else profile_data.date_of_birth
            ),
            gender=profile_data.gender,
            weight_kg=profile_data.weight_kg,
            known_allergies=sanitize_text_input(profile_data.known_allergies or "", max_length=500) or None,
            medical_conditions=sanitize_text_input(profile_data.medical_conditions or "", max_length=1000) or None,
            is_primary=False,
        )
        self.db.add(profile)
        await self.db.flush()

        await self.audit.log(
            event_type=AuditEventType.PROFILE_CREATED,
            outcome=AuditOutcome.SUCCESS,
            user_id=user_id,
            profile_id=profile.id,
            request_id=request_id,
        )

        logger.info("profile_created", user_id=user_id, profile_id=profile.id)
        return profile

    async def update_profile(self, profile_id: str, user_id: str, update_data: ProfileUpdate, request_id: str = "unknown") -> Profile:
        from core.security import sanitize_text_input
        from services.sharing_service import SharingService

        profile = await self.get_profile(profile_id=profile_id, user_id=user_id, request_id=request_id)
        # Viewers cannot update profile data — caregiver minimum required
        role = await SharingService(db=self.db).get_user_role_for_profile(
            profile_id=profile_id, user_id=user_id
        )
        if not role or role == "viewer":
            from core.exceptions import AuthorizationError
            raise AuthorizationError("Viewers cannot update profile data.")
        updates = update_data.model_dump(exclude_unset=True)

        for forbidden_field in ("id", "user_id", "is_primary", "created_at"):
            updates.pop(forbidden_field, None)

        for field, value in updates.items():
            if isinstance(value, str):
                value = sanitize_text_input(value)
            setattr(profile, field, value)

        if updates.get("name") and updates["name"].strip().lower() != "me":
            from sqlalchemy import select
            from models.user import User
            user_result = await self.db.execute(select(User).where(User.id == user_id))
            user_obj = user_result.scalar_one_or_none()
            if user_obj and not user_obj.onboarding_completed:
                user_obj.onboarding_completed = True

        await self.audit.log(
            event_type=AuditEventType.PROFILE_UPDATED,
            outcome=AuditOutcome.SUCCESS,
            user_id=user_id,
            profile_id=profile_id,
            request_id=request_id,
        )
        return profile

    async def delete_profile(self, profile_id: str, user_id: str, request_id: str = "unknown") -> None:
        from services.sharing_service import SharingService

        profile = await self.get_profile(profile_id=profile_id, user_id=user_id, request_id=request_id)
        # Only owners can delete profiles
        role = await SharingService(db=self.db).get_user_role_for_profile(
            profile_id=profile_id, user_id=user_id
        )
        if role != "owner":
            from core.exceptions import AuthorizationError
            raise AuthorizationError("Only the profile owner can delete a profile.")

        if profile.is_primary:
            raise AuthorizationError("Cannot delete your primary profile. Create another profile first.")

        await self.db.delete(profile)

        await self.audit.log(
            event_type=AuditEventType.PROFILE_DELETED,
            outcome=AuditOutcome.SUCCESS,
            user_id=user_id,
            profile_id=profile_id,
            request_id=request_id,
        )
        logger.info("profile_deleted", user_id=user_id, profile_id=profile_id)