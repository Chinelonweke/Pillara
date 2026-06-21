# monitoring/audit.py
#
# WHY HIPAA REQUIRES AUDIT LOGS:
# HIPAA Security Rule §164.312(b) requires:
# "Implement hardware, software, and/or procedural mechanisms that
# record and examine activity in information systems that contain
# or use electronic protected health information."
#
# In plain English: log every time PHI is accessed, modified, or deleted.
#
# WHAT AUDIT LOGS CAPTURE:
# - Who accessed what (user_id, profile_id)
# - When they accessed it (timestamp, always UTC)
# - What they did (event type: viewed medications, ran interaction check)
# - What the outcome was (success, failure, denied)
# - What system did it (request_id, IP hash)
#
# WHAT AUDIT LOGS DO NOT CAPTURE:
# - The actual PHI content (that would make the audit log itself PHI)
# - Medication names or dosages
# - Conversation content
# - Diagnostic information
#
# WHY AUDIT LOGS ARE DIFFERENT FROM APPLICATION LOGS:
# Application logs: debugging aid, can be deleted/rotated, verbose
# Audit logs: legal record, must be retained 6 years (HIPAA), minimal data
#
# AUDIT LOG PROPERTIES:
# - Write-only from the application (no UPDATE or DELETE)
# - Append-only — even if a user deletes their account, audit logs stay
# - Retained 6 years (HIPAA minimum for business associates)
# - No foreign key constraints (survive user/profile deletion)

from enum import Enum
from typing import Optional

from monitoring.logger import get_logger

logger = get_logger(__name__)


# ─── AUDIT EVENT TYPES ────────────────────────────────────────────────────────
#
# WHY AN ENUM:
# Using string literals ("user_login") means typos are silent bugs.
# Using an Enum means AuditEventType.USER_LOGIN is checked at import time.
# If the enum value doesn't exist, Python raises an AttributeError immediately.

class AuditEventType(str, Enum):
    """
    All auditable events in Pillara.

    WHY str ENUM:
    Inheriting from str means the enum value IS a string.
    AuditEventType.USER_LOGIN == "user_login" → True
    This lets us store the string in the database without conversion.
    """
    # Authentication events
    USER_REGISTERED      = "user_registered"
    USER_LOGIN           = "user_login"
    USER_LOGOUT          = "user_logout"
    USER_LOGOUT_ALL      = "user_logout_all"
    LOGIN_FAILED         = "login_failed"
    PASSWORD_RESET       = "password_reset"
    PASSWORD_CHANGED     = "password_changed"
    TOKEN_REFRESHED      = "token_refreshed"
    EMAIL_VERIFIED       = "email_verified"

    # Profile events
    PROFILE_CREATED      = "profile_created"
    PROFILE_VIEWED       = "profile_viewed"
    PROFILE_UPDATED      = "profile_updated"
    PROFILE_DELETED      = "profile_deleted"

    # Medication events (PHI access — most important to audit)
    MEDICATION_ADDED     = "medication_added"
    MEDICATION_VIEWED    = "medication_viewed"
    MEDICATION_UPDATED   = "medication_updated"
    MEDICATION_DELETED   = "medication_deleted"
    MEDICATIONS_LISTED   = "medications_listed"

    # AI usage events
    INTERACTION_CHECKED  = "drug_interaction_checked"
    AI_QUERY_MADE        = "ai_query_made"
    VOICE_QUERY_MADE     = "voice_query_made"

    # Report events
    REPORT_GENERATED     = "medication_report_generated"
    REPORT_DOWNLOADED    = "medication_report_downloaded"

    # Reminder events
    REMINDER_CREATED     = "reminder_created"
    REMINDER_DELETED     = "reminder_deleted"

    # Admin events
    ADMIN_ACCESS         = "admin_access"
    DATA_EXPORT          = "data_exported"


class AuditOutcome(str, Enum):
    """Whether the audited action succeeded or failed."""
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED  = "denied"   # access was attempted but permission was denied


# ─── AUDIT LOGGER ─────────────────────────────────────────────────────────────

class AuditLogger:
    """
    Writes to the HIPAA-compliant audit log.

    IMPORTANT: This class writes to two places:
    1. The AuditLog database table (primary — permanent record)
    2. The structured log output (secondary — for real-time monitoring)

    WHY BOTH:
    Database: queryable ("show me all medication access events for user X")
    Log output: streamable to SIEM (security monitoring tools like Splunk, Datadog)

    USAGE:
        audit = AuditLogger(db_session)
        await audit.log(
            event_type=AuditEventType.MEDICATION_VIEWED,
            user_id=user_id,
            outcome=AuditOutcome.SUCCESS,
            request_id=request_id,
        )
    """

    def __init__(self, db=None):
        """
        db: optional AsyncSession for database writes.
        If not provided, logs to structured log only (useful in tests).
        """
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
        """
        Records an auditable event.

        PARAMETERS:
        event_type:    What happened (from AuditEventType enum)
        outcome:       Did it succeed, fail, or get denied?
        user_id:       Who did it (UUID, not name or email)
        profile_id:    Which profile was affected (if applicable)
        request_id:    The HTTP request that triggered this event
        ip_hash:       Anonymised IP address (never raw IP)
        resource_type: What type of thing was affected ("medication", "profile")
        resource_id:   The UUID of the specific thing affected
        details:       Optional extra context — must NOT contain PHI

        WHY user_id (not email/name):
        User IDs are random UUIDs — they don't identify a person to a reader.
        An email address or name in an audit log IS PHI.
        The audit log links to the user table by ID, but the log entry itself
        does not contain personal information.
        """
        # Write to structured log (always happens, even if DB write fails)
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
            # WHY NOT LOG 'details':
            # details might contain information a developer put there
            # thinking it was safe, but actually isn't.
            # We log the structured fields only. Details stay in the DB.
        )

        # Write to database (the permanent legal record)
        if self.db:
            await self._write_to_database(
                event_type=event_type,
                outcome=outcome,
                user_id=user_id,
                profile_id=profile_id,
                request_id=request_id,
                ip_hash=ip_hash,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
            )

    async def _write_to_database(
        self,
        event_type: AuditEventType,
        outcome: AuditOutcome,
        user_id: Optional[str],
        profile_id: Optional[str],
        request_id: Optional[str],
        ip_hash: Optional[str],
        resource_type: Optional[str],
        resource_id: Optional[str],
        details: Optional[dict],
    ) -> None:
        """
        Writes the audit event to the AuditLog database table.

        WHY A PRIVATE METHOD (_write_to_database):
        The underscore prefix signals "internal implementation detail."
        Callers use .log(), not ._write_to_database() directly.
        """
        from datetime import datetime, timezone
        from sqlalchemy import text
        import json

        # WHY RAW SQL (not SQLAlchemy ORM):
        # The audit log must ALWAYS be written, even if there's an ORM issue.
        # Raw SQL is more reliable and has fewer dependencies.
        # Also, we're INSERT-only — no updates, no deletes, no ORM needed.
        #
        # WHY text() WITH NAMED PARAMETERS:
        # text() with :parameter_name syntax uses parameterized queries.
        # This prevents SQL injection — the database driver handles escaping.
        # NEVER concatenate user data into SQL strings directly.

        now = datetime.now(tz=timezone.utc)
        details_json = json.dumps(details) if details else None

        try:
            await self.db.execute(
                text("""
                    INSERT INTO audit_logs (
                        user_id,
                        profile_id,
                        event_type,
                        outcome,
                        resource_type,
                        resource_id,
                        request_id,
                        ip_hash,
                        details,
                        created_at
                    ) VALUES (
                        :user_id,
                        :profile_id,
                        :event_type,
                        :outcome,
                        :resource_type,
                        :resource_id,
                        :request_id,
                        :ip_hash,
                        :details,
                        :created_at
                    )
                """),
                {
                    "user_id":       user_id,
                    "profile_id":    profile_id,
                    "event_type":    event_type.value,
                    "outcome":       outcome.value,
                    "resource_type": resource_type,
                    "resource_id":   resource_id,
                    "request_id":    request_id,
                    "ip_hash":       ip_hash,
                    "details":       details_json,
                    "created_at":    now,
                }
            )
            # WHY NOT COMMIT HERE:
            # The database session is committed by the get_db dependency
            # after the request handler completes successfully.
            # If we committed here and the request later failed,
            # we'd have an audit record for something that didn't happen.

        except Exception as error:
            # WHY NOT RAISE:
            # If the audit log write fails, we should NOT fail the request.
            # The user's operation should complete even if audit logging has an issue.
            # We log the failure — which will itself be captured — and continue.
            # HIPAA note: persistent audit log failures should trigger an alert
            # and be investigated. We add a sentry capture here.
            logger.error(
                "audit_log_write_failed",
                error=str(error),
                event_type=event_type.value,
                request_id=request_id,
            )

            try:
                import sentry_sdk
                sentry_sdk.capture_exception(error)
            except Exception:
                pass  # sentry failure is non-fatal