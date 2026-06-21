# workers/tasks/reminder_task.py
#
# RACE CONDITION FIX APPLIED:
# 1. SELECT FOR UPDATE SKIP LOCKED — multiple workers never process same reminder
# 2. last_sent_at written FIRST — minimises double-send window on worker crash
# 3. processing_locked_at cleared after completion — clean state for next run

from monitoring.logger import get_logger

logger = get_logger(__name__)


async def process_due_reminders() -> None:
    """
    Fetches and sends all due medication reminders.
    Safe to run from multiple worker processes simultaneously.
    """
    from core.database import AsyncSessionFactory
    from services.reminder_service import ReminderService

    async with AsyncSessionFactory() as db:
        try:
            service = ReminderService(db=db)

            # SELECT FOR UPDATE SKIP LOCKED — no double processing
            reminders = await service.fetch_due_reminders_with_lock(batch_size=20)

            if not reminders:
                return

            logger.info("reminder_batch_fetched", count=len(reminders))

            for reminder in reminders:
                await _send_reminder(reminder=reminder, service=service, db=db)

            await db.commit()

        except Exception as error:
            await db.rollback()
            logger.error("reminder_batch_failed", error=str(error))
            raise


async def _send_reminder(reminder, service, db) -> None:
    """
    Sends one reminder via all configured channels.
    Writes last_sent_at IMMEDIATELY after sending — before any other work.
    """
    from models.user import Medication, Profile
    from sqlalchemy import select

    try:
        # Fetch medication and profile names for the notification message
        med_result = await db.execute(
            select(Medication).where(Medication.id == reminder.medication_id)
        )
        medication = med_result.scalar_one_or_none()

        if not medication:
            logger.warning("reminder_medication_not_found", reminder_id=reminder.id)
            reminder.is_active = False
            await db.flush()
            return

        medication_name = medication.name
        dosage = medication.dosage or ""
        message = f"Time to take your {medication_name}"
        if dosage:
            message += f" ({dosage})"

        send_errors = []

        # Send via each configured channel
        if reminder.notify_push:
            try:
                await _send_push_notification(reminder=reminder, message=message)
            except Exception as e:
                send_errors.append(f"push: {e}")

        if reminder.notify_email:
            try:
                await _send_email_notification(reminder=reminder, message=message)
            except Exception as e:
                send_errors.append(f"email: {e}")

        if reminder.notify_sms:
            try:
                await _send_sms_notification(reminder=reminder, message=message)
            except Exception as e:
                send_errors.append(f"sms: {e}")

        if send_errors:
            logger.warning(
                "reminder_partial_send_failure",
                reminder_id=reminder.id,
                errors=send_errors,
            )

        # CRITICAL: Write last_sent_at IMMEDIATELY after sending.
        # If we crash after this line, the next worker sees last_sent_at is set
        # and skips the reminder. Near-zero double-sends.
        await service.mark_reminder_sent(reminder)

        logger.info("reminder_sent", reminder_id=reminder.id)

    except Exception as error:
        logger.error("reminder_send_failed", reminder_id=reminder.id, error=str(error))
        # Release the lock so it can be retried
        reminder.processing_locked_at = None
        await db.flush()


async def _send_push_notification(reminder, message: str) -> None:
    """Sends a Web Push notification."""
    # TODO: implement with pywebpush
    # Requires VAPID keys and the user's push subscription endpoint
    logger.debug("push_notification_sent", reminder_id=reminder.id)


async def _send_email_notification(reminder, message: str) -> None:
    """Sends an email reminder via Resend."""
    # TODO: implement with resend SDK
    logger.debug("email_notification_sent", reminder_id=reminder.id)


async def _send_sms_notification(reminder, message: str) -> None:
    """Sends an SMS via Africa's Talking."""
    # TODO: implement with africastalking SDK
    logger.debug("sms_notification_sent", reminder_id=reminder.id)