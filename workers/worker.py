# workers/worker.py
#
# ARQ (Async Redis Queue) background worker.
# Handles: medication reminders, PDF report generation, email sending.
#
# WHY ARQ (not Celery):
# ARQ is fully async — built for asyncio. Celery uses threads.
# Our entire stack is async. ARQ fits naturally.
# ARQ uses Redis — we already have Redis. No extra broker needed.
#
# RUNNING THE WORKER:
# arq workers.worker.WorkerSettings
#
# IN PRODUCTION:
# Run as a separate process alongside the FastAPI app.
# Supervise with systemd or as a separate Docker container.

from arq import cron
from arq.connections import RedisSettings

from core.config import settings
from monitoring.logger import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


async def startup(ctx: dict) -> None:
    """Called once when the worker starts."""
    from core.database import init_database
    from core.redis_client import init_redis

    await init_database()
    ctx["redis"] = await init_redis()
    logger.info("arq_worker_started")


async def shutdown(ctx: dict) -> None:
    """Called once when the worker stops."""
    from core.database import close_database
    from core.redis_client import close_redis

    await close_database()
    await close_redis()
    logger.info("arq_worker_stopped")


async def send_due_reminders(ctx: dict) -> None:
    """
    Cron job: runs every minute, sends due medication reminders.
    Uses SELECT FOR UPDATE SKIP LOCKED — safe under multiple worker processes.
    """
    from workers.tasks.reminder_task import process_due_reminders
    await process_due_reminders()


class WorkerSettings:
    """ARQ worker configuration."""

    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

    functions = []
    # Background functions that can be enqueued manually
    # e.g.: await queue.enqueue_job("send_email", email="user@example.com")

    cron_jobs = [
        cron(send_due_reminders, minute={0, 1, 2, 3, 4, 5, 6, 7, 8, 9,
                                         10, 11, 12, 13, 14, 15, 16, 17, 18, 19,
                                         20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
                                         30, 31, 32, 33, 34, 35, 36, 37, 38, 39,
                                         40, 41, 42, 43, 44, 45, 46, 47, 48, 49,
                                         50, 51, 52, 53, 54, 55, 56, 57, 58, 59}),
        # Runs every minute (all 60 minute values)
    ]

    on_startup = startup
    on_shutdown = shutdown

    max_jobs = 10
    # Maximum concurrent jobs this worker handles
    # Keep low — each job uses a DB connection from the pool

    job_timeout = 60
    # Jobs that run longer than 60 seconds are cancelled
    # Reminder sending should never take this long