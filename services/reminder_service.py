# services/reminder_service.py
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import NotFoundError
from models.user import Medication, Profile, Reminder
from monitoring.audit import AuditEventType, AuditLogger, AuditOutcome
from monitoring.logger import get_logger
from schemas.all_schemas import ReminderCreate

logger = get_logger(__name__)


class ReminderService:

    def __init__(self, db: AsyncSession, redis=None):
        self.db = db
        self.audit = AuditLogger(db=db)

    async def list_reminders(self, profile_id: str, user_id: str) -> list[Reminder]:
        """IDOR safe: joins through Profile to verify user_id."""
        result = await self.db.execute(
            select(Reminder)
            .join(Profile, Reminder.profile_id == Profile.id)
            .where(
                Profile.user_id == user_id,
                Reminder.profile_id == profile_id,
                Reminder.is_active.is_(True),
            )
            .order_by(Reminder.next_send_at.asc())
        )
        return list(result.scalars().all())

    async def create_reminder(
        self,
        profile_id: str,
        user_id: str,
        reminder_data: ReminderCreate,
        request_id: str = "unknown",
    ) -> Reminder:
        # Verify profile ownership
        profile_result = await self.db.execute(
            select(Profile).where(Profile.id == profile_id, Profile.user_id == user_id)
        )
        if not profile_result.scalar_one_or_none():
            raise NotFoundError("Profile")

        # Verify medication belongs to this profile (also an IDOR check)
        med_result = await self.db.execute(
            select(Medication).where(
                Medication.id == reminder_data.medication_id,
                Medication.profile_id == profile_id,
                Medication.is_active.is_(True),
            )
        )
        if not med_result.scalar_one_or_none():
            raise NotFoundError("Medication")

        reminder = Reminder(
            profile_id=profile_id,
            medication_id=reminder_data.medication_id,
            reminder_time=reminder_data.reminder_time,
            is_recurring=reminder_data.is_recurring,
            recurrence_rule=reminder_data.recurrence_rule,
            notify_push=reminder_data.notify_push,
            notify_email=reminder_data.notify_email,
            notify_sms=reminder_data.notify_sms,
            is_active=True,
            next_send_at=reminder_data.reminder_time,
        )
        self.db.add(reminder)
        await self.db.flush()

        await self.audit.log(
            event_type=AuditEventType.REMINDER_CREATED,
            outcome=AuditOutcome.SUCCESS,
            user_id=user_id,
            profile_id=profile_id,
            resource_type="reminder",
            resource_id=reminder.id,
            request_id=request_id,
        )

        return reminder

    async def delete_reminder(self, reminder_id: str, user_id: str, request_id: str = "unknown") -> None:
        result = await self.db.execute(
            select(Reminder)
            .join(Profile, Reminder.profile_id == Profile.id)
            .where(Reminder.id == reminder_id, Profile.user_id == user_id)
        )
        reminder = result.scalar_one_or_none()
        if not reminder:
            raise NotFoundError("Reminder")

        reminder.is_active = False

        await self.audit.log(
            event_type=AuditEventType.REMINDER_DELETED,
            outcome=AuditOutcome.SUCCESS,
            user_id=user_id,
            resource_type="reminder",
            resource_id=reminder_id,
            request_id=request_id,
        )

    async def fetch_due_reminders_with_lock(self, batch_size: int = 10) -> list[Reminder]:
        now = datetime.now(tz=timezone.utc)
        stale_lock_threshold = now - timedelta(minutes=5)

        result = await self.db.execute(
            select(Reminder)
            .where(
                Reminder.is_active.is_(True),
                Reminder.next_send_at <= now,
                # Either not locked, or lock is stale (worker crashed >5 min ago)
                (Reminder.processing_locked_at.is_(None)) |
                (Reminder.processing_locked_at < stale_lock_threshold),
            )
            .limit(batch_size)
            .with_for_update(skip_locked=True)
            # FOR UPDATE: lock these rows for our transaction
            # SKIP LOCKED: if another worker has locked a row, skip it — don't wait
        )
        reminders = list(result.scalars().all())

        # Mark as being processed
        for reminder in reminders:
            reminder.processing_locked_at = now

        await self.db.flush()

        return reminders

    async def mark_reminder_sent(self, reminder: Reminder) -> None:
        now = datetime.now(tz=timezone.utc)
        reminder.last_sent_at = now
        reminder.processing_locked_at = None  # Release the lock

        if reminder.is_recurring and reminder.recurrence_rule:
            # Calculate next send time from recurrence rule
            reminder.next_send_at = self._calculate_next_send(
                reminder.reminder_time,
                reminder.recurrence_rule,
                now,
            )
        else:
            # One-time reminder — deactivate it
            reminder.is_active = False
            reminder.next_send_at = None

        await self.db.flush()

    def _calculate_next_send(
        self,
        base_time: datetime,
        recurrence_rule: str,
        after: datetime,
    ) -> datetime:
        """
        Calculates the next send time from an iCal RRULE string.
        FREQ=DAILY → next day at same time
        FREQ=WEEKLY → next week at same time
        """
        rule_upper = recurrence_rule.upper()

        if "FREQ=DAILY" in rule_upper:
            next_time = after + timedelta(days=1)
            return next_time.replace(
                hour=base_time.hour,
                minute=base_time.minute,
                second=0,
                microsecond=0,
            )
        elif "FREQ=WEEKLY" in rule_upper:
            next_time = after + timedelta(weeks=1)
            return next_time.replace(
                hour=base_time.hour,
                minute=base_time.minute,
                second=0,
                microsecond=0,
            )
        elif "FREQ=HOURLY" in rule_upper:
            return after + timedelta(hours=1)
        else:
            # Unknown rule — default to daily
            logger.warning("unknown_recurrence_rule", rule=recurrence_rule)
            return after + timedelta(days=1)