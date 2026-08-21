# monitoring/audit.py
from enum import Enum
from typing import Optional

from monitoring.logger import get_logger

logger = get_logger(__name__)


class AuditEventType(str, Enum):
    USER_REGISTERED      = "user_registered"
    USER_LOGIN           = "user_login"
    USER_LOGOUT          = "user_logout"
    USER_LOGOUT_ALL      = "user_logout_all"
    LOGIN_FAILED         = "login_failed"
    PASSWORD_RESET       = "password_reset"
    PASSWORD_CHANGED     = "password_changed"
    TOKEN_REFRESHED      = "token_refreshed"
    EMAIL_VERIFIED       = "email_verified"
    PROFILE_CREATED      = "profile_created"
    PROFILE_VIEWED       = "profile_viewed"
    PROFILE_UPDATED      = "profile_updated"
    PROFILE_DELETED      = "profile_deleted"
    PROFILE_INVITE_SENT      = "profile_invite_sent"
    PROFILE_INVITE_ACCEPTED  = "profile_invite_accepted"
    PROFILE_ACCESS_REVOKED   = "profile_access_revoked"
    PROFILE_CLAIMED          = "profile_claimed"
    MEDICATION_ADDED     = "medication_added"
    MEDICATION_VIEWED    = "medication_viewed"
    MEDICATION_UPDATED   = "medication_updated"
    MEDICATION_DELETED   = "medication_deleted"
    MEDICATIONS_LISTED   = "medications_listed"
    INTERACTION_CHECKED  = "drug_interaction_checked"
    AI_QUERY_MADE        = "ai_query_made"
    VOICE_QUERY_MADE     = "voice_query_made"
    REPORT_GENERATED     = "medication_report_generated"
    REPORT_DOWNLOADED    = "medication_report_downloaded"
    REMINDER_CREATED     = "reminder_created"
    REMINDER_DELETED     = "reminder_deleted"
    ADMIN_ACCESS         = "admin_access"
    DATA_EXPORT          = "data_exported"


class AuditOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED  = "denied"


class AuditLogger:
    """Writes HIPAA-compliant audit events to database and structured log. Never raises."""

    def __init__(self, db=None):
        self.db = db
        self.logger = get_logger("audit")

    async def log(
        self,
        event_type: AuditEventType,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        user_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        request_id: Optional[str] = None,
        ip_hash: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        self.logger.info(
            "audit_event",
            event_type=event_type.value,
            outcome=outcome.value,
            user_id=user_id,
            profile_id=profile_id,
            request_id=request_id,
            ip_hash=ip_hash,
            resource_type=resource_type,
            resource_id=resource_id,
        )

        if self.db:
            await self._write_to_database(
                event_type=event_type, outcome=outcome, user_id=user_id,
                profile_id=profile_id, request_id=request_id, ip_hash=ip_hash,
                resource_type=resource_type, resource_id=resource_id, details=details,
            )

    async def _write_to_database(self, event_type, outcome, user_id, profile_id,
                                   request_id, ip_hash, resource_type, resource_id, details) -> None:
        from datetime import datetime, timezone
        from sqlalchemy import text
        import json

        now = datetime.now(tz=timezone.utc)
        details_json = json.dumps(details) if details else None

        try:
            await self.db.execute(
                text("""
                    INSERT INTO audit_logs (
                        user_id, profile_id, event_type, outcome,
                        resource_type, resource_id, request_id, ip_hash, details, created_at
                    ) VALUES (
                        :user_id, :profile_id, :event_type, :outcome,
                        :resource_type, :resource_id, :request_id, :ip_hash, :details, :created_at
                    )
                """),
                {
                    "user_id": user_id, "profile_id": profile_id,
                    "event_type": event_type.value, "outcome": outcome.value,
                    "resource_type": resource_type, "resource_id": resource_id,
                    "request_id": request_id, "ip_hash": ip_hash,
                    "details": details_json, "created_at": now,
                }
            )
        except Exception as error:
            logger.error("audit_log_write_failed", error=str(error), event_type=event_type.value)
            try:
                import sentry_sdk
                sentry_sdk.capture_exception(error)
            except Exception:
                pass