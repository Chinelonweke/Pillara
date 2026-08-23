# monitoring/analytics.py
#
# PostHog tracks product usage events — not system health (that's Prometheus).
# Three events for now: registered, medication_added, interaction_checked.
# These answer: "Are users actually using the product?"

from monitoring.logger import get_logger

logger = get_logger(__name__)

_posthog = None


def _get_posthog():
    global _posthog
    if _posthog is not None:
        return _posthog

    from core.config import settings
    if not settings.POSTHOG_API_KEY:
        return None

    try:
        from posthog import Posthog
        _posthog = Posthog(
            project_api_key=settings.POSTHOG_API_KEY,
            host='https://app.posthog.com',
        )
        import logging
        logging.getLogger('posthog').setLevel(logging.WARNING)
        return _posthog
    except Exception as error:
        logger.warning("posthog_init_failed", error=str(error))
        return None


def track(event: str, user_id: str, properties: dict = None) -> None:
    """
    Tracks a product event in PostHog.
    Never raises — analytics failure must never affect user requests.
    """
    client = _get_posthog()
    if not client:
        return

    try:
        client.capture(
            distinct_id=user_id,
            event=event,
            properties=properties or {},
        )
    except Exception as error:
        logger.warning("posthog_track_failed", event=event, error=str(error))