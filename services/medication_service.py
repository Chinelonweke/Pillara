# services/medication_service.py
#
# IDOR ENFORCEMENT: Every query joins through Profile to verify user_id ownership.
# No query ever fetches a medication by ID alone.
# Pattern: JOIN medications → profiles WHERE profiles.user_id = :current_user_id
#
# AUDIT LOGGING: Written here in the service, not in the route.
# If this service is ever called from a background job, the audit still fires.
#
# DATA FRESHNESS: When a medication is added, we note when FDA data was fetched.
# A background job can later check for medications with stale FDA data and re-fetch.

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import (
    DuplicateMedicationError,
    MedicationNotFoundError,
)
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
        Base query that joins Medication → Profile and filters by user_id.
        This is the IDOR guard — every medication query uses this as its base.

        WHY A HELPER METHOD:
        Ensures every query in this service enforces ownership.
        Copy-paste mistakes (forgetting the JOIN) are impossible
        when all queries start from this single base.
        """
        return (
            select(Medication)
            .join(Profile, Medication.profile_id == Profile.id)
            .where(Profile.user_id == user_id)
            # This WHERE clause is what makes it IDOR-safe.
            # profile.user_id must match the authenticated user.
        )

    async def list_medications(
        self,
        profile_id: str,
        user_id: str,
        include_inactive: bool = False,
        request_id: str = "unknown",
    ) -> list[Medication]:
        """
        Lists medications for a profile, with ownership verification.
        The profile_id filter + user_id join means:
        - Correct user, correct profile → gets medications
        - Correct user, wrong profile → gets empty list (their own profile has no match)
        - Wrong user, any profile → gets empty list (user_id doesn't match)
        No 403 or 404 leaks whether a profile exists for another user.
        """
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

    async def get_medication(
        self,
        medication_id: str,
        user_id: str,
        request_id: str = "unknown",
    ) -> Medication:
        """
        Fetches one medication with ownership verification.
        Returns 404 whether the medication doesn't exist OR belongs to another user.
        """
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

        # DATA FRESHNESS WARNING
        self._check_fda_data_freshness(medication)

        return medication

    async def add_medication(
        self,
        profile_id: str,
        user_id: str,
        medication_data: MedicationCreate,
        request_id: str = "unknown",
    ) -> Medication:
        """
        Adds a medication to a profile.

        OWNERSHIP CHECK: verify the profile belongs to user_id before adding.
        This prevents adding medications to someone else's profile
        by supplying a foreign profile_id.
        """
        # Verify profile ownership — prevents IDOR on profile_id
        profile_result = await self.db.execute(
            select(Profile).where(
                Profile.id == profile_id,
                Profile.user_id == user_id,
            )
        )
        profile = profile_result.scalar_one_or_none()
        if not profile:
            raise MedicationNotFoundError(medication_id=profile_id)
        # We return MedicationNotFoundError (not ProfileNotFoundError)
        # to avoid revealing that we found the profile but the user doesn't own it.

        # Check for duplicate active medication
        sanitized_name = sanitize_medication_name(medication_data.name)
        existing_result = await self.db.execute(
            self._ownership_query(user_id).where(
                Medication.profile_id == profile_id,
                Medication.name.ilike(sanitized_name),
                # ilike = case-insensitive LIKE — "Ibuprofen" matches "ibuprofen"
                Medication.is_active == True,
            )
        )
        if existing_result.scalar_one_or_none():
            raise DuplicateMedicationError(medication_name=sanitized_name)

        medication = Medication(
            profile_id=profile_id,
            # profile_id from the verified profile — never from request body directly
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
            # Will be set when we fetch FDA data in the background
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

        logger.info(
            "medication_added",
            user_id=user_id,
            profile_id=profile_id,
            medication_id=medication.id,
        )

        return medication

    async def update_medication(
        self,
        medication_id: str,
        user_id: str,
        update_data: MedicationUpdate,
        request_id: str = "unknown",
    ) -> Medication:
        """
        Updates a medication.
        IDOR: ownership verified via _ownership_query.
        MASS ASSIGNMENT: only fields in MedicationUpdate schema are applied.
        MedicationUpdate deliberately excludes: id, profile_id, user_id.
        """
        medication = await self.get_medication(
            medication_id=medication_id,
            user_id=user_id,
            request_id=request_id,
        )

        updates = update_data.model_dump(exclude_unset=True)

        # Explicit mass assignment protection — belt and suspenders
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

    async def delete_medication(
        self,
        medication_id: str,
        user_id: str,
        request_id: str = "unknown",
    ) -> None:
        """
        Soft-delete: sets is_active=False.
        The medication record is retained for audit history and
        HIPAA retention requirements — we never hard-delete health records.
        """
        medication = await self.get_medication(
            medication_id=medication_id,
            user_id=user_id,
            request_id=request_id,
        )

        medication.is_active = False

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
        """
        Logs a warning if FDA data for this medication is older than 90 days.
        Does not block the request — just flags for the ops team.
        """
        if not medication.fda_data_fetched_at:
            logger.warning(
                "medication_no_fda_data",
                medication_id=medication.id,
            )
            return

        age_days = (datetime.now(tz=timezone.utc) - medication.fda_data_fetched_at).days
        if age_days > 90:
            logger.warning(
                "stale_medication_fda_data",
                medication_id=medication.id,
                age_days=age_days,
            )