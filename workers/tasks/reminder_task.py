# workers/tasks/reminder_task.py

from monitoring.logger import get_logger

logger = get_logger(__name__)


async def process_due_reminders() -> None:
    """
    Fetches and sends all due medication reminders.
    Safe to run from multiple worker processes simultaneously.
    Uses SELECT FOR UPDATE SKIP LOCKED to prevent double-sends.
    """
    from core.database import AsyncSessionFactory
    from services.reminder_service import ReminderService

    async with AsyncSessionFactory() as db:
        try:
            service = ReminderService(db=db)
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
    Writes last_sent_at IMMEDIATELY after sending to prevent double-sends on crash.
    """
    from models.user import Medication, Profile, User
    from sqlalchemy import select

    try:
        # Fetch medication details
        med_result = await db.execute(
            select(Medication).where(Medication.id == reminder.medication_id)
        )
        medication = med_result.scalar_one_or_none()

        if not medication:
            logger.warning("reminder_medication_not_found", reminder_id=reminder.id)
            reminder.is_active = False
            await db.flush()
            return

        # Fetch profile and user for notification context
        profile_result = await db.execute(
            select(Profile).where(Profile.id == reminder.profile_id)
        )
        profile = profile_result.scalar_one_or_none()

        user_email = None
        profile_name = profile.name if profile else ""

        if profile:
            user_result = await db.execute(
                select(User).where(User.id == profile.user_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                user_email = user.email

        medication_name = medication.name
        dosage = medication.dosage or ""

        send_errors = []

        # Email notification
        if reminder.notify_email and user_email:
            try:
                await _send_email_notification(
                    to_email=user_email,
                    medication_name=medication_name,
                    dosage=dosage,
                    profile_name=profile_name,
                )
            except Exception as e:
                send_errors.append(f"email: {e}")

        # Push notification (stub — implement with pywebpush post-launch)
        if reminder.notify_push:
            try:
                await _send_push_notification(
                    reminder=reminder,
                    medication_name=medication_name,
                    dosage=dosage,
                )
            except Exception as e:
                send_errors.append(f"push: {e}")

        # SMS notification (stub — implement with Africa's Talking post-launch)
        if reminder.notify_sms and user_email:
            try:
                await _send_sms_notification(
                    reminder=reminder,
                    medication_name=medication_name,
                )
            except Exception as e:
                send_errors.append(f"sms: {e}")

        if send_errors:
            logger.warning(
                "reminder_partial_send_failure",
                reminder_id=reminder.id,
                errors=send_errors,
            )

        # CRITICAL: Write last_sent_at IMMEDIATELY after sending.
        # If worker crashes after this line, the next run sees last_sent_at
        # and skips this reminder. Prevents double-sends.
        await service.mark_reminder_sent(reminder)

        logger.info(
            "reminder_sent",
            reminder_id=reminder.id,
            medication=medication_name,
            channels_attempted=["email" if reminder.notify_email else None,
                                 "push" if reminder.notify_push else None],
        )

    except Exception as error:
        logger.error("reminder_send_failed", reminder_id=reminder.id, error=str(error))
        # Release the processing lock so it can be retried next minute
        reminder.processing_locked_at = None
        await db.flush()


async def _send_email_notification(
    to_email: str,
    medication_name: str,
    dosage: str,
    profile_name: str,
) -> None:
    """Sends a branded medication reminder email via Resend."""
    from services.email_service import send_reminder_email
    success = await send_reminder_email(
        to_email=to_email,
        medication_name=medication_name,
        dosage=dosage,
        profile_name=profile_name,
    )
    if not success:
        raise RuntimeError(f"send_reminder_email returned False for {to_email}")


async def _send_push_notification(reminder, medication_name: str, dosage: str) -> None:
    """
    Web Push notification — not yet implemented.
    Requires VAPID keys and user's push subscription stored in database.
    Implement post-launch with pywebpush library.
    """
    logger.debug("push_notification_stub", reminder_id=reminder.id, medication=medication_name)


async def _send_sms_notification(reminder, medication_name: str) -> None:
    """
    SMS via Africa's Talking — not yet implemented.
    Best delivery channel for Nigerian users without smartphones.
    Implement post-launch with africastalking library.
    """
    logger.debug("sms_notification_stub", reminder_id=reminder.id, medication=medication_name)