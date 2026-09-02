# monitoring/sentry_setup.py
from core.config import settings
from monitoring.logger import get_logger

logger = get_logger(__name__)


def init_sentry() -> None:
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
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        before_send=_scrub_phi_from_event,
        send_default_pii=False,
    )
    logger.info("sentry_initialized", environment=settings.ENVIRONMENT)


def _scrub_phi_from_event(event: dict, hint: dict) -> dict | None:
    # Drop ChromaDB telemetry noise — third-party library bug
    exc_info = hint.get("exc_info")
    if exc_info:
        exc_type, exc_value, _ = exc_info
        if exc_type is TypeError and "capture() takes 1 positional argument" in str(exc_value):
            return None

    if "chromadb.telemetry" in event.get("logger", ""):
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

    if "request" in event:
        event["request"] = scrub_dict(event["request"])
    if "extra" in event:
        event["extra"] = scrub_dict(event["extra"])
    if "exception" in event and "values" in event["exception"]:
        for exc_value in event["exception"]["values"]:
            if "stacktrace" in exc_value and "frames" in exc_value["stacktrace"]:
                for frame in exc_value["stacktrace"]["frames"]:
                    if "vars" in frame:
                        frame["vars"] = scrub_dict(frame["vars"])

    return event