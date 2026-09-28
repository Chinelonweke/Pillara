# workers/tasks/reminder_recovery_task.py
#
# WHAT THIS DOES:
# Runs every 10 minutes. Finds reminders that should have sent but didn't —
# detected by next_send_at being in the past but the reminder still active.
# This covers cases where the ARQ worker crashed mid-processing.
#
# WHY THIS IS NEEDED:
# The main reminder task uses SELECT FOR UPDATE SKIP LOCKED — if a worker crashes
# while holding a lock, that lock is released but the reminder's next_send_at
# is not updated, leaving it in a "stuck" state.

from datetime import datetime, timezone, timedelta

from monitoring.logger import get_logger
logger = get_logger(__name__)


async def recover_missed_reminders(ctx) -> None:
    """
    ARQ task: finds reminders overdue by more than 15 minutes and re-sends them.
    Runs every 10 minutes via cron.
    """
    from sqlalchemy import select, and_
    from core.database import AsyncSessionFactory
    from models.user import Reminder, Profile, User, Medication

    now = datetime.now(timezone.utc)
    # A reminder is "missed" if it was due more than 15 minutes ago
    # (gives the normal reminder task a window to process it first)
    missed_cutoff = now - timedelta(minutes=15)
    # Same staleness window the main task uses for its own lock (reminder_service.py) —
    # a fresh lock means the main task (or another recovery run) is actively sending
    # this reminder right now, so leave it alone to avoid a duplicate send.
    stale_lock_threshold = now - timedelta(minutes=5)

    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(Reminder, Profile, User, Medication)
            .join(Profile, Reminder.profile_id == Profile.id)
            .join(User, Profile.user_id == User.id)
            .join(Medication, Reminder.medication_id == Medication.id)
            .where(
                and_(
                    Reminder.is_active.is_(True),
                    Reminder.next_send_at <= missed_cutoff,
                    Medication.is_active.is_(True),
                    (Reminder.processing_locked_at.is_(None)) |
                    (Reminder.processing_locked_at < stale_lock_threshold),
                )
            )
            .limit(50)  # Process max 50 at a time to avoid overloading email
            .with_for_update(of=Reminder, skip_locked=True)
        )

        rows = result.all()

        if not rows:
            logger.debug("reminder_recovery_no_missed_reminders")
            return

        logger.warning(
            "reminder_recovery_found_missed",
            count=len(rows),
        )

        # Claim the lock on all of them up front, in the same transaction that
        # holds the SKIP LOCKED row locks above — mirrors fetch_due_reminders_with_lock.
        for reminder, _profile, _user, _medication in rows:
            reminder.processing_locked_at = now
        await db.flush()

        from services.reminder_service import ReminderService
        reminder_service = ReminderService(db)

        for reminder, profile, user, medication in rows:
            try:
                # Send the missed reminder email
                from services.email_service import send_reminder_email
                await send_reminder_email(
                    to_email=user.email,
                    profile_name=profile.name,
                    medication_name=medication.name,
                    dosage=medication.dosage,
                )

                # Update next_send_at so it doesn't get picked up again
                await reminder_service.mark_reminder_sent(reminder)

                logger.info(
                    "reminder_recovery_sent",
                    reminder_id=str(reminder.id),
                    medication=medication.name,
                )

            except Exception as error:
                logger.error(
                    "reminder_recovery_failed",
                    reminder_id=str(reminder.id),
                    error=str(error),
                )
                reminder.processing_locked_at = None  # release lock so it can be retried sooner
                continue

        await db.commit()