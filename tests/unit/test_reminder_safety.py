# tests/unit/test_reminder_safety.py
#
# Regression tests for three patient-safety bugs:
# 1. Reminders kept firing for discontinued (soft-deleted) medications.
# 2. The missed-reminder recovery cron always crashed silently and never sent.
# 3. The recovery cron could double-send a reminder the main task already sent.

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.reminder_service import ReminderService
from services.email_service import send_reminder_email


@pytest.mark.asyncio
async def test_fetch_due_reminders_excludes_inactive_medications():
    """A soft-deleted/discontinued medication must not have its reminders sent."""
    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()

    service = ReminderService(db=mock_db)
    await service.fetch_due_reminders_with_lock(batch_size=5)

    executed_query = mock_db.execute.call_args[0][0]
    compiled = str(executed_query.compile(compile_kwargs={"literal_binds": False})).lower()
    assert "medications" in compiled  # joins to the medications table
    assert compiled.count("is_active") >= 2  # filters both Reminder.is_active and Medication.is_active


def test_send_reminder_email_signature_matches_recovery_task_call():
    """The recovery task must call send_reminder_email with kwargs that actually
    exist on the function (a mismatched keyword raises TypeError, silently
    swallowed by the task's broad except, which made the recovery cron a no-op)."""
    params = set(inspect.signature(send_reminder_email).parameters)
    assert {"to_email", "medication_name", "dosage", "profile_name"} <= params


def test_reminder_recovery_task_calls_existing_service_method():
    """The recovery task previously called ReminderService.advance_next_send_at,
    a method that doesn't exist, raising AttributeError on every recovery run."""
    import workers.tasks.reminder_recovery_task as recovery_module

    source = inspect.getsource(recovery_module.recover_missed_reminders)
    assert "advance_next_send_at" not in source
    assert "mark_reminder_sent" in source
    assert hasattr(ReminderService, "mark_reminder_sent")


class _FakeSessionContextManager:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc_info):
        return False


@pytest.mark.asyncio
async def test_recovery_task_locks_rows_to_avoid_double_send():
    """The recovery task must lock/skip reminders the main task (or another
    recovery run) already holds a fresh processing lock on, and must claim the
    lock on rows it picks up — otherwise it can re-send a reminder that was
    already sent, or race a concurrent run."""
    import workers.tasks.reminder_recovery_task as recovery_module

    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []  # no missed reminders — just inspect the query built
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("core.database.AsyncSessionFactory", return_value=_FakeSessionContextManager(mock_db)):
        await recovery_module.recover_missed_reminders(ctx={})

    executed_query = mock_db.execute.call_args[0][0]
    compiled = str(executed_query.compile(compile_kwargs={"literal_binds": False})).lower()
    assert "for update" in compiled
    assert "processing_locked_at" in compiled
