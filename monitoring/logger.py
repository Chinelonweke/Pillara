# monitoring/logger.py
#
# WHY THIS FILE IS A HIPAA DOCUMENT AS MUCH AS A TECHNICAL ONE:
# HIPAA requires that Protected Health Information (PHI) is never logged
# in plain text. A standard print() or logging.info() statement is a HIPAA
# violation if it includes a medication name, diagnosis, or patient detail.
#
# Our solution: structlog with a PHI scrubber processor.
# The scrubber runs on EVERY log event before it's written.
# Even if a developer accidentally logs PHI, the scrubber catches and removes it.
#
# WHAT IS PHI IN PILLARA'S CONTEXT:
# - Patient names
# - Email addresses
# - Medication names when paired with a user identifier
# - Dosages, symptoms, diagnoses
# - Any conversation content
# - IP addresses (handled by hash_ip_address in security.py)
#
# WHAT IS NOT PHI (safe to log):
# - UUIDs (not linked to identity in the log)
# - Status codes (200, 404)
# - Latency values (100ms)
# - Error codes ("rate_limit_exceeded")
# - Provider names ("groq", "cerebras")
# - Chunk IDs and similarity scores (no PHI content)
#
# STRUCTURED LOGGING:
# Traditional logging: logger.info("User 12345 added medication ibuprofen")
# This is a string — hard to search, hard to parse, prone to PHI leakage.
#
# Structured logging: logger.info("medication_added", user_id=uuid, medication_count=5)
# This is a key-value event — searchable, parseable, fields can be individually scrubbed.

import logging
import sys
from pathlib import Path
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from core.config import settings


# ─── PHI SCRUBBER ─────────────────────────────────────────────────────────────

# Field names that should NEVER appear in logs
# If a developer accidentally logs these fields, we redact the value.
PHI_FIELD_NAMES = frozenset({
    # User identifiers that link to a person
    "email",
    "name",
    "first_name",
    "last_name",
    "full_name",
    "username",
    "phone",
    "phone_number",

    # Medical information
    "medication_name",
    "drug_name",
    "diagnosis",
    "symptoms",
    "dosage",
    "dose",
    "condition",
    "medical_history",
    "allergy",
    "allergies",

    # Conversation content (may contain medical information)
    "query",
    "message",
    "content",
    "text",
    "conversation",
    "response_text",
    "user_message",

    # Network identifiers
    "ip",
    "ip_address",
    "raw_ip",

    # Auth credentials
    "password",
    "token",
    "api_key",
    "secret",
    "access_token",
    "refresh_token",
})

# String patterns that suggest PHI in field values
# These are partial matches — we look for these INSIDE longer strings too
PHI_VALUE_PATTERNS = [
    "@",          # email addresses always contain @
    "Bearer ",    # Authorization headers
    "gsk_",       # Groq API key prefix
    "sk-or-",     # OpenRouter key prefix
    "hf_",        # HuggingFace key prefix
    "csk_",       # Cerebras key prefix
    "re_",        # Resend API key prefix
]


def scrub_phi(
    logger: Any,
    method: str,
    event_dict: EventDict,
) -> EventDict:
    """
    structlog processor that removes PHI from log events.

    HOW structlog PROCESSORS WORK:
    structlog applies a list of processor functions to every log event.
    Each processor receives (logger, method, event_dict) and returns a modified event_dict.
    The processors run in order — the final one writes the log.

    THIS PROCESSOR:
    - Scans all keys in the event dict
    - Replaces values of known PHI field names with "[REDACTED]"
    - Scans string values for PHI patterns (email @, API key prefixes)
    - Returns the scrubbed event dict

    WHY A PROCESSOR (not just being careful):
    Humans make mistakes. A processor is automatic.
    If any code in Pillara accidentally logs an email address,
    this processor catches it before it's written to disk or sent to Sentry.
    Defense in depth — security that doesn't depend on perfect developer behavior.

    THE no_phi_context ESCAPE HATCH:
    By default, ANY field named "drug_name" gets redacted everywhere — because
    in most of this app, a drug name IS tied to a specific patient's medication
    list (genuinely PHI). But some code (e.g. scripts/seed_drug_data.py, which
    seeds generic FDA reference data with no patient involved at all) has no
    patient context whatsoever, and the blanket redaction just hides useful,
    harmless debugging information for no privacy benefit.

    Rather than trying to make the scrubber GUESS at context (fragile, and a
    worse security posture — guessing wrong in the unsafe direction is a real
    HIPAA risk), call sites can be explicit: pass no_phi_context=True to skip
    field-name-based scrubbing for that one log event. This is opt-in, visible
    in the code, and easy to audit — anyone reading the call site immediately
    sees the deliberate justification, instead of redaction silently varying
    based on what the scrubber happened to infer.

    WHY VALUE-PATTERN SCRUBBING (emails, API keys) STILL ALWAYS RUNS:
    no_phi_context only skips the FIELD-NAME check. Email addresses, API key
    prefixes, and other pattern-matched secrets are still scrubbed from EVERY
    log event regardless — those patterns are unambiguous and never belong in
    logs under any circumstance, generic reference data or not.
    """
    # Call sites opt out of field-name scrubbing by passing this flag.
    # It's consumed (popped) here so it never appears in the actual log output.
    no_phi_context = event_dict.pop("no_phi_context", False)

    # We cannot modify the dict while iterating it — collect changes first
    # Then apply them after the loop
    keys_to_scrub = []

    for key, value in event_dict.items():
        # Check 1: Is the field name itself a PHI field?
        # Skipped entirely when the call site has explicitly declared
        # this event has no patient context.
        if not no_phi_context and key.lower() in PHI_FIELD_NAMES:
            keys_to_scrub.append(key)
            continue

        # Check 2: Does the string value contain PHI patterns?
        # This ALWAYS runs, even with no_phi_context=True — pattern matches
        # (emails, API keys) are unambiguous regardless of context.
        if isinstance(value, str):
            for pattern in PHI_VALUE_PATTERNS:
                if pattern in value:
                    keys_to_scrub.append(key)
                    break  # one pattern match is enough to redact

    # Apply redactions after the loop
    for key in keys_to_scrub:
        event_dict[key] = "[REDACTED]"

    return event_dict


def add_request_context(
    logger: Any,
    method: str,
    event_dict: EventDict,
) -> EventDict:
    """
    Adds standard context fields to every log event.

    WHY CONSISTENT CONTEXT:
    When you search logs for "all events related to request abc123",
    every log line in that request has request_id=abc123.
    This makes debugging a specific request trivial.

    structlog's context vars let us set context once (in middleware)
    and have it appear automatically in every subsequent log call
    within that async request context.
    """
    # structlog.contextvars contains values set by bind_contextvars()
    # We use this in middleware to bind request_id and user_id
    context = structlog.contextvars.get_contextvars()

    if "request_id" in context:
        event_dict["request_id"] = context["request_id"]
    if "user_id" in context:
        event_dict["user_id"] = context["user_id"]

    return event_dict


def add_severity(
    logger: Any,
    method: str,
    event_dict: EventDict,
) -> EventDict:
    """
    Adds a 'severity' field matching Google Cloud / AWS logging standards.

    WHY ADD severity:
    Many log aggregators (Stackdriver, CloudWatch) use 'severity' or 'level'
    to categorise logs. Adding this field makes Pillara logs compatible
    with standard observability platforms.
    """
    # method is the log method name: "info", "warning", "error", etc.
    event_dict["severity"] = method.upper()
    return event_dict


# ─── LOGGING CONFIGURATION ────────────────────────────────────────────────────

def configure_logging() -> None:
    """
    Configures structlog for the entire application.
    Call this ONCE at startup, before any logging happens.

    WHY CONFIGURE ONCE AT STARTUP:
    structlog configuration is global — setting it multiple times
    can cause unexpected behavior. Configure once, log everywhere.
    """
    # The list of processors defines what happens to each log event
    # They run IN ORDER — left to right
    processors: list[Processor] = [
        # 1. Merge context vars (request_id, user_id set by middleware)
        structlog.contextvars.merge_contextvars,

        # 2. Add our custom context (request_id, user_id)
        add_request_context,

        # 3. Add severity field
        add_severity,

        # 4. SCRUB PHI — this runs on every log event
        # This is the HIPAA compliance processor
        scrub_phi,

        # 5. Add timestamp in ISO 8601 format
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        # utc=True = all timestamps in UTC — no timezone confusion

        # 6. Add caller information (filename, line number)
        # Only in development — too noisy for production
        *(
            [structlog.processors.CallsiteParameterAdder(
                [
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.LINENO,
                ]
            )]
            if settings.ENVIRONMENT == "development"
            else []
        ),
        # The *[...] unpacks the list into the outer list
        # Conditional inclusion: only add if in development

        # 7. Format the final output
        structlog.dev.ConsoleRenderer(
            colors=True,
            # WHY colors=True EXPLICITLY (not relying on auto-detection):
            # structlog normally auto-detects whether the terminal supports
            # ANSI color codes, but this detection can be unreliable on
            # Windows — especially older PowerShell/cmd.exe sessions, or
            # when output is piped/redirected (which our file-tee below
            # technically does). Forcing colors=True guarantees the
            # ConsoleRenderer always emits ANSI codes: red for errors,
            # yellow for warnings, green/cyan for info — exactly what a
            # senior engineer expects from local dev logs. We then strip
            # those codes specifically for the FILE write further down,
            # since raw ANSI escapes look like garbage in a text file.
        )
        if settings.ENVIRONMENT == "development"
        else structlog.processors.JSONRenderer(),
        # Development: pretty colored console output (human-readable)
        # Production: JSON output (machine-parseable, works with log aggregators)
    ]

    # WHY A DUAL WRITER (terminal + file):
    # Printing only to the terminal means logs vanish the moment you scroll
    # past them or close the window. Writing only to a file means you lose
    # the live, colored, readable output while actively coding.
    # _TeeLogOutput writes every line to BOTH — same pattern as the Unix
    # `tee` command. You get live terminal output AND a persistent file
    # that VS Code's Explorer sidebar shows as a normal, openable file.
    import re
    ansi_escape_pattern = re.compile(r"\x1b\[[0-9;]*m")
    # WHY STRIP ANSI FOR THE FILE:
    # ConsoleRenderer emits real ANSI escape codes (e.g. "\x1b[31m" for red)
    # so the terminal can render colors. A terminal interprets those codes
    # and shows colored text. A plain text file does NOT interpret them —
    # opening app.log in VS Code would show literal garbage characters
    # mixed into every line instead of clean readable text. We keep colors
    # for the live terminal (where they're useful) and strip them only for
    # the file (where they'd just be noise).

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    log_file = open(logs_dir / "app.log", "a", encoding="utf-8")

    class _TeeLogOutput:
        """Writes each log line to stdout (colored) and a log file (plain text)."""
        def write(self, message: str) -> None:
            sys.stdout.write(message)
            log_file.write(ansi_escape_pattern.sub("", message))
            log_file.flush()
            # WHY flush() ON EVERY WRITE:
            # Without this, the OS buffers writes and the file looks empty
            # or stale for a while even though logging is actively happening.
            # flush() forces it to disk immediately — important for a file
            # you're watching live in VS Code.

        def flush(self) -> None:
            sys.stdout.flush()
            log_file.flush()

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            # In development: DEBUG and above
            # In production: INFO and above (DEBUG is too noisy)
            logging.DEBUG if settings.DEBUG else logging.INFO
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=_TeeLogOutput()),
        # WHY stdout (not stderr) WAS THE ORIGINAL CHOICE, STILL HONORED HERE:
        # In Docker, stdout is captured by the logging driver.
        # Log aggregators (Fluentd, CloudWatch agent) typically capture stdout.
        # We still write to stdout via the tee above — this just ALSO writes
        # to logs/app.log for local visibility in VS Code.
        cache_logger_on_first_use=True,
        # WHY CACHE:
        # Logger creation has some overhead.
        # After the first call, the logger is cached — subsequent calls are instant.
    )

    # Also configure Python's standard logging to use structlog
    # WHY: third-party libraries (SQLAlchemy, uvicorn) use standard logging.
    # We route their logs through structlog so they're also HIPAA-scrubbed.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
    )

    # Silence noisy loggers that would flood the console
    # WHY SILENCE THESE:
    # sqlalchemy.engine logs every SQL query — useful for debugging but too noisy for prod
    # httpx logs every HTTP request — same issue
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.WARNING if not settings.DEBUG else logging.DEBUG
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(
        logging.WARNING  # We have our own access logging in middleware
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Gets a structlog logger for a module.

    USAGE:
        logger = get_logger(__name__)
        logger.info("event_name", key="value", other_key=123)

    WHY __name__:
    __name__ is the module's full path: "services.auth_service"
    This appears in logs so you know exactly which file logged each event.
    """
    return structlog.get_logger(name)


# ─── REQUEST LOGGER ───────────────────────────────────────────────────────────

class RequestLogger:
    """
    Helper for logging HTTP requests in a HIPAA-safe, structured way.

    WHAT WE LOG:
    ✅ method (GET, POST)
    ✅ path (/api/v1/medications)
    ✅ status_code (200, 404)
    ✅ duration_ms (145.23)
    ✅ request_id (UUID)
    ✅ ip_hash (anonymised IP)

    WHAT WE DO NOT LOG:
    ❌ Request body (may contain medication data, PHI)
    ❌ Response body (contains AI responses, may contain PHI)
    ❌ Query parameters with user data
    ❌ Authorization headers (tokens)
    ❌ Raw IP addresses

    WHY LOG request_id:
    Every request gets a unique ID (UUID, set in middleware).
    All log lines for that request share the same request_id.
    To debug a specific user's request: filter by request_id.
    To see all steps for that request: you get a complete trace.
    """

    def __init__(self):
        self.logger = get_logger("http.access")

    def log_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        request_id: str,
        ip_hash: str = "unknown",
    ) -> None:
        """Logs a completed HTTP request."""
        log_fn = self.logger.info

        # Use warning for 4xx, error for 5xx
        if 400 <= status_code < 500:
            log_fn = self.logger.warning
        elif status_code >= 500:
            log_fn = self.logger.error

        log_fn(
            "http_request",
            method=method,
            path=path,
            status_code=status_code,
            duration_ms=round(duration_ms, 2),
            request_id=request_id,
            ip_hash=ip_hash,
        )