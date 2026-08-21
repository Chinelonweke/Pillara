from datetime import datetime, timezone

from sqlalchemy import select
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
        """Base query joining Medication → Profile filtering by user_id. All queries use this for IDOR protection."""
        return (
            select(Medication)
            .join(Profile, Medication.profile_id == Profile.id)
            .where(Profile.user_id == user_id)
        )

    async def list_medications(self, profile_id: str, user_id: str, include_inactive: bool = False, request_id: str = "unknown") -> list[Medication]:
        query = (
            self._ownership_query(user_id)
            .where(Medication.profile_id == profile_id)
            .order_by(Medication.created_at.desc())
        )
        if not include_inactive:
            query = query.where(Medication.is_active == True)

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
        profile_result = await self.db.execute(
            select(Profile).where(Profile.id == profile_id, Profile.user_id == user_id)
        )
        if not profile_result.scalar_one_or_none():
            raise MedicationNotFoundError(medication_id=profile_id)

        sanitized_name = sanitize_medication_name(medication_data.name)
        existing_result = await self.db.execute(
            self._ownership_query(user_id).where(
                Medication.profile_id == profile_id,
                Medication.name.ilike(sanitized_name),
                Medication.is_active == True,
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
        return medication

    async def update_medication(self, medication_id: str, user_id: str, update_data: MedicationUpdate, request_id: str = "unknown") -> Medication:
        medication = await self.get_medication(medication_id=medication_id, user_id=user_id, request_id=request_id)
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
        medication = await self.get_medication(medication_id=medication_id, user_id=user_id, request_id=request_id)
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