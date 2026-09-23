from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import DuplicateMedicationError, MedicationNotFoundError
from core.security import sanitize_medication_name, sanitize_text_input
from models.user import Medication, Profile
from monitoring.audit import AuditEventType, AuditLogger, AuditOutcome
from monitoring.logger import get_logger
from schemas.all_schemas import MedicationCreate, MedicationUpdate

logger = get_logger(__name__)


class MedicationService:

    def __init__(self, db: AsyncSession, redis=None):
        self.db = db
        self.audit = AuditLogger(db=db)

    def _ownership_query(self, user_id: str):
        """
        Base query joining Medication → Profile.
        Checks both direct ownership (user_id) AND shared access (owner_user_id or ProfileAccess).
        This allows caregivers and owners to access medications they are authorized for.
        The role is verified at the API dependency layer (get_profile_from_query).
        Here we simply verify the profile exists and the user has some access to it.
        """
        from models.user import ProfileAccess
        return (
            select(Medication)
            .join(Profile, Medication.profile_id == Profile.id)
            .where(
                or_(
                    Profile.user_id == user_id,
                    Profile.owner_user_id == user_id,
                    Profile.id.in_(
                        select(ProfileAccess.profile_id).where(
                            and_(
                                ProfileAccess.granted_to_user_id == user_id,
                                ProfileAccess.status == "active",
                            )
                        )
                    ),
                )
            )
        )

    async def list_medications(self, profile_id: str, user_id: str, include_inactive: bool = False, request_id: str = "unknown") -> list[Medication]:
        query = (
            self._ownership_query(user_id)
            .where(Medication.profile_id == profile_id)
            .order_by(Medication.created_at.desc())
        )
        if not include_inactive:
            query = query.where(Medication.is_active.is_(True))

        result = await self.db.execute(query)
        medications = list(result.scalars().all())

        await self.audit.log(
            event_type=AuditEventType.MEDICATIONS_LISTED,
            outcome=AuditOutcome.SUCCESS,
            user_id=user_id,
            profile_id=profile_id,
            request_id=request_id,
            resource_type="medication_list",
        )
        return medications

    async def get_medication(self, medication_id: str, user_id: str, request_id: str = "unknown") -> Medication:
        result = await self.db.execute(
            self._ownership_query(user_id).where(Medication.id == medication_id)
        )
        medication = result.scalar_one_or_none()
        if not medication:
            raise MedicationNotFoundError(medication_id=medication_id)

        await self.audit.log(
            event_type=AuditEventType.MEDICATION_VIEWED,
            outcome=AuditOutcome.SUCCESS,
            user_id=user_id,
            resource_type="medication",
            resource_id=medication_id,
            request_id=request_id,
        )
        self._check_fda_data_freshness(medication)
        return medication

    async def add_medication(self, profile_id: str, user_id: str, medication_data: MedicationCreate, request_id: str = "unknown") -> Medication:
        # Role-aware: owners and caregivers can add medications. Viewers cannot.
        from services.sharing_service import SharingService
        role = await SharingService(db=self.db).get_user_role_for_profile(
            profile_id=profile_id, user_id=user_id
        )
        if not role or role == "viewer":
            from core.exceptions import AuthorizationError
            raise AuthorizationError("Viewers cannot add medications.")

        sanitized_name = sanitize_medication_name(medication_data.name)
        existing_result = await self.db.execute(
            self._ownership_query(user_id).where(
                Medication.profile_id == profile_id,
                Medication.name.ilike(sanitized_name),
                Medication.is_active.is_(True),
            )
        )
        if existing_result.scalar_one_or_none():
            raise DuplicateMedicationError(medication_name=sanitized_name)

        medication = Medication(
            profile_id=profile_id,
            name=sanitized_name,
            generic_name=sanitize_medication_name(medication_data.generic_name or ""),
            dosage=sanitize_text_input(medication_data.dosage or "", max_length=100),
            frequency=sanitize_text_input(medication_data.frequency or "", max_length=100),
            route=sanitize_text_input(medication_data.route or "", max_length=50),
            prescribed_by=sanitize_text_input(medication_data.prescribed_by or "", max_length=200),
            start_date=medication_data.start_date,
            end_date=medication_data.end_date,
            purpose=sanitize_text_input(medication_data.purpose or "", max_length=500),
            notes=sanitize_text_input(medication_data.notes or "", max_length=1000),
            is_active=True,
            fda_data_fetched_at=None,
        )
        self.db.add(medication)
        await self.db.flush()

        await self.audit.log(
            event_type=AuditEventType.MEDICATION_ADDED,
            outcome=AuditOutcome.SUCCESS,
            user_id=user_id,
            profile_id=profile_id,
            resource_type="medication",
            resource_id=medication.id,
            request_id=request_id,
        )
        logger.info("medication_added", user_id=user_id, profile_id=profile_id, medication_id=medication.id)

        from monitoring.analytics import track
        track("medication_added", user_id=str(user_id), properties={"profile_id": str(profile_id)})
        return medication

    async def update_medication(self, medication_id: str, user_id: str, update_data: MedicationUpdate, request_id: str = "unknown") -> Medication:
        # Viewers cannot update medications — caregiver minimum required
        medication = await self.get_medication(medication_id=medication_id, user_id=user_id, request_id=request_id)
        from services.sharing_service import SharingService
        role = await SharingService(db=self.db).get_user_role_for_profile(
            profile_id=str(medication.profile_id), user_id=user_id
        )
        if not role or role == "viewer":
            from core.exceptions import AuthorizationError
            raise AuthorizationError("Viewers cannot update medications.")
        updates = update_data.model_dump(exclude_unset=True)

        for forbidden in ("id", "profile_id", "user_id", "created_at", "fda_data_fetched_at"):
            updates.pop(forbidden, None)

        for field, value in updates.items():
            if field == "name" and value:
                value = sanitize_medication_name(value)
            elif isinstance(value, str):
                value = sanitize_text_input(value)
            setattr(medication, field, value)

        await self.audit.log(
            event_type=AuditEventType.MEDICATION_UPDATED,
            outcome=AuditOutcome.SUCCESS,
            user_id=user_id,
            resource_type="medication",
            resource_id=medication_id,
            request_id=request_id,
        )
        return medication

    async def delete_medication(self, medication_id: str, user_id: str, request_id: str = "unknown") -> None:
        # Viewers cannot delete medications — caregiver minimum required
        medication = await self.get_medication(medication_id=medication_id, user_id=user_id, request_id=request_id)
        from services.sharing_service import SharingService
        role = await SharingService(db=self.db).get_user_role_for_profile(
            profile_id=str(medication.profile_id), user_id=user_id
        )
        if not role or role == "viewer":
            from core.exceptions import AuthorizationError
            raise AuthorizationError("Viewers cannot delete medications.")
        medication.is_active = False  # Soft delete — retain for HIPAA audit history

        await self.audit.log(
            event_type=AuditEventType.MEDICATION_DELETED,
            outcome=AuditOutcome.SUCCESS,
            user_id=user_id,
            resource_type="medication",
            resource_id=medication_id,
            request_id=request_id,
        )
        logger.info("medication_soft_deleted", medication_id=medication_id, user_id=user_id)

    def _check_fda_data_freshness(self, medication: Medication) -> None:
        if not medication.fda_data_fetched_at:
            logger.warning("medication_no_fda_data", medication_id=medication.id)
            return
        age_days = (datetime.now(tz=timezone.utc) - medication.fda_data_fetched_at).days
        if age_days > 90:
            logger.warning("stale_medication_fda_data", medication_id=medication.id, age_days=age_days)