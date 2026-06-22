# monitoring/sentry_setup.py
#
# Sentry captures unhandled exceptions with full context for investigation.
# HIPAA NOTE: Sentry's before_send hook scrubs PHI before events are sent,
# mirroring the scrub_phi processor in monitoring/logger.py.

from core.config import settings
from monitoring.logger import get_logger

logger = get_logger(__name__)


def init_sentry() -> None:
    """Initializes Sentry error tracking. Call once at app startup."""
    if not settings.SENTRY_DSN:
        logger.info("sentry_not_configured")
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        release=settings.APP_VERSION,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
        before_send=_scrub_phi_from_event,
        # WHY before_send: Sentry events can contain request bodies, local
        # variables, and stack trace context — all potential PHI sources.
        # This hook runs before ANY event leaves our server.
        send_default_pii=False,
        # NEVER send default PII (IP addresses, cookies, etc.) — HIPAA requirement
    )
    logger.info("sentry_initialized", environment=settings.ENVIRONMENT)


def _scrub_phi_from_event(event: dict, hint: dict) -> dict | None:
    """
    Runs before every event is sent to Sentry. Two jobs:

    1. FILTER known third-party noise — returns None to drop the event
       entirely, so it never reaches Sentry and never pollutes the feed.

    2. SCRUB PHI — removes patient-identifiable fields from request bodies,
       local variables, and stack trace context before the event leaves
       our server. Mirrors the PHI_FIELD_NAMES scrubbing in logger.py.

    WHY FILTER HERE (not ignore_errors=[TypeError]):
    ignore_errors suppresses ALL TypeErrors, including real ones in our
    own code that we genuinely need to see. Filtering in before_send
    lets us be surgical — we check the specific error message and logger
    name, so only this exact third-party noise is dropped, nothing else.
    """
    # ── Filter ChromaDB telemetry noise ────────────────────────────────────────
    # ChromaDB's internal telemetry client has a known bug: it calls
    # capture() with the wrong number of arguments, producing:
    # "Failed to send telemetry event ClientStartEvent: capture() takes
    # 1 positional argument but 3 were given"
    # This is a third-party library bug we cannot fix. It has zero impact
    # on Pillara's functionality. Dropping it here keeps the Issues feed
    # clean so real errors are immediately visible.
    exc_info = hint.get("exc_info")
    if exc_info:
        exc_type, exc_value, _ = exc_info
        if (
            exc_type is TypeError
            and "capture() takes 1 positional argument" in str(exc_value)
        ):
            return None  # Drop this event entirely — never reaches Sentry

    # Also filter by logger name as a secondary check
    logger_name = event.get("logger", "")
    if "chromadb.telemetry" in logger_name:
        return None

    from monitoring.logger import PHI_FIELD_NAMES

    def scrub_dict(d: dict) -> dict:
        if not isinstance(d, dict):
            return d
        scrubbed = {}
        for key, value in d.items():
            if key.lower() in PHI_FIELD_NAMES:
                scrubbed[key] = "[REDACTED]"
            elif isinstance(value, dict):
                scrubbed[key] = scrub_dict(value)
            elif isinstance(value, list):
                scrubbed[key] = [scrub_dict(v) if isinstance(v, dict) else v for v in value]
            else:
                scrubbed[key] = value
        return scrubbed

    # Scrub request data
    if "request" in event:
        event["request"] = scrub_dict(event["request"])

    # Scrub extra context
    if "extra" in event:
        event["extra"] = scrub_dict(event["extra"])

    # Scrub local variables in stack traces
    if "exception" in event and "values" in event["exception"]:
        for exc_value in event["exception"]["values"]:
            if "stacktrace" in exc_value and "frames" in exc_value["stacktrace"]:
                for frame in exc_value["stacktrace"]["frames"]:
                    if "vars" in frame:
                        frame["vars"] = scrub_dict(frame["vars"])

    return event