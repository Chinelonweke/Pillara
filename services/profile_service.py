from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import AuthorizationError, ProfileNotFoundError
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
        result = await self.db.execute(
            select(Profile).where(Profile.id == profile_id, Profile.user_id == user_id)
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
            date_of_birth=profile_data.date_of_birth,
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

        profile = await self.get_profile(profile_id=profile_id, user_id=user_id, request_id=request_id)
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
        profile = await self.get_profile(profile_id=profile_id, user_id=user_id, request_id=request_id)

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