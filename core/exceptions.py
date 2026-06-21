# core/exceptions.py
#
# WHY CUSTOM EXCEPTIONS:
# Python's built-in exceptions (ValueError, RuntimeError) tell you WHAT went wrong
# but not WHY or WHERE in the context of Pillara.
# Custom exceptions let you:
# 1. Catch specific error types: except MedicationNotFoundError (not generic Exception)
# 2. Attach structured data: error.medication_id, error.user_id
# 3. Map to HTTP status codes: NotFoundError → 404, AuthError → 401
# 4. Log meaningfully: every exception has a code and message by design
#
# HOW THE HIERARCHY WORKS:
# PillaraError (base)
# ├── AuthenticationError   → 401
# ├── AuthorizationError    → 403
# ├── NotFoundError         → 404
# ├── ValidationError       → 422
# ├── ConflictError         → 409
# ├── RateLimitError        → 429
# ├── AIServiceError        → 503
# └── DatabaseError         → 500
#
# Every exception maps to one HTTP status code.
# The FastAPI error handler (in main.py) reads the status_code
# and returns the right HTTP response automatically.


class PillaraError(Exception):
    """
    Base exception for all Pillara errors.

    WHY A BASE CLASS:
    Lets you catch ANY Pillara error in one except clause:
        except PillaraError as error:
            handle_any_app_error(error)

    Or catch specific errors:
        except AuthenticationError:
            redirect_to_login()

    ATTRIBUTES:
    message:     Human-readable error description (safe to show users)
    code:        Machine-readable error code (for frontend to handle)
    status_code: HTTP status code this error maps to
    details:     Optional dict with extra context (for logging, not shown to users)
    """

    def __init__(
        self,
        message: str,
        code: str = "internal_error",
        status_code: int = 500,
        details: dict = None,
    ):
        # super().__init__(message) calls the parent Exception class __init__
        # This makes the error message available via str(error)
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        # {} as default is safer than None — callers can always do error.details.get(...)

    def to_dict(self) -> dict:
        """
        Converts the exception to a dict for JSON API responses.

        WHY NOT INCLUDE 'details' IN THE RESPONSE:
        details may contain internal information (stack traces, DB query params)
        that should NEVER be exposed to API consumers.
        details is for internal logging only.
        """
        return {
            "error": self.code,
            "message": self.message,
        }


# ─── AUTHENTICATION & AUTHORIZATION ───────────────────────────────────────────

class AuthenticationError(PillaraError):
    """
    User is not authenticated (no token, expired token, invalid token).
    → HTTP 401 Unauthorized

    WHY 401 vs 403:
    401 = "I don't know who you are" (no valid credentials)
    403 = "I know who you are, but you can't do this" (no permission)
    """
    def __init__(self, message: str = "Authentication required", details: dict = None):
        super().__init__(
            message=message,
            code="authentication_required",
            status_code=401,
            details=details or {},
        )


class InvalidTokenError(PillaraError):
    """JWT token is malformed, expired, or has been revoked."""
    def __init__(self, message: str = "Token is invalid or has expired"):
        super().__init__(
            message=message,
            code="invalid_token",
            status_code=401,
        )


class AuthorizationError(PillaraError):
    """
    User is authenticated but not allowed to perform this action.
    → HTTP 403 Forbidden

    Example: User A trying to view User B's medications.
    """
    def __init__(self, message: str = "You do not have permission to do this"):
        super().__init__(
            message=message,
            code="permission_denied",
            status_code=403,
        )


# ─── RESOURCE ERRORS ──────────────────────────────────────────────────────────

class NotFoundError(PillaraError):
    """
    Requested resource does not exist.
    → HTTP 404 Not Found

    WHY NOT EXPOSE WHETHER A RESOURCE EXISTS:
    In some contexts (user lookups during login), you don't want to reveal
    whether an email address is registered. In those cases, raise
    AuthenticationError("Invalid email or password") instead of
    NotFoundError("User not found").
    """
    def __init__(self, resource: str = "Resource", resource_id: str = None):
        message = f"{resource} not found"
        if resource_id:
            message = f"{resource} '{resource_id}' not found"
        super().__init__(
            message=message,
            code="not_found",
            status_code=404,
            details={"resource": resource, "resource_id": resource_id},
        )


class MedicationNotFoundError(NotFoundError):
    """Specific case: medication record not found."""
    def __init__(self, medication_id: str = None):
        super().__init__(resource="Medication", resource_id=medication_id)
        self.code = "medication_not_found"


class ProfileNotFoundError(NotFoundError):
    """Specific case: user profile not found."""
    def __init__(self, profile_id: str = None):
        super().__init__(resource="Profile", resource_id=profile_id)
        self.code = "profile_not_found"


# ─── VALIDATION ERRORS ────────────────────────────────────────────────────────

class ValidationError(PillaraError):
    """
    Input data failed validation (invalid drug name, bad date format, etc.)
    → HTTP 422 Unprocessable Entity

    WHY 422 vs 400:
    400 = the request is malformed (bad JSON, missing required field)
    422 = the request is well-formed but the data is semantically wrong
    FastAPI uses Pydantic for 400/422 automatically — this class handles
    business-logic validation that Pydantic can't express.

    Example: A medication name that passes Pydantic's string validation
    but fails our drug name whitelist check → ValidationError.
    """
    def __init__(self, message: str, field: str = None):
        super().__init__(
            message=message,
            code="validation_error",
            status_code=422,
            details={"field": field} if field else {},
        )


class DrugNameInvalidError(ValidationError):
    """Drug name not found in our validated drug database."""
    def __init__(self, drug_name: str):
        super().__init__(
            message=f"'{drug_name}' is not a recognised medication name. "
                    f"Please check the spelling or search for the generic name.",
            field="drug_name",
        )
        self.code = "invalid_drug_name"


class InvalidAudioError(ValidationError):
    """Audio file is too large, wrong format, or unreadable."""
    def __init__(self, reason: str = "Invalid audio file"):
        super().__init__(message=reason, field="audio")
        self.code = "invalid_audio"


# ─── CONFLICT ERRORS ──────────────────────────────────────────────────────────

class ConflictError(PillaraError):
    """
    Request conflicts with existing data.
    → HTTP 409 Conflict

    Example: Trying to register with an email that already exists.
    """
    def __init__(self, message: str = "A conflict occurred with existing data"):
        super().__init__(
            message=message,
            code="conflict",
            status_code=409,
        )


class EmailAlreadyExistsError(ConflictError):
    """Email address is already registered."""
    def __init__(self):
        super().__init__(
            message="An account with this email address already exists. "
                    "Please sign in or use a different email."
        )
        self.code = "email_already_exists"


class DuplicateMedicationError(ConflictError):
    """User is trying to add a medication they already have."""
    def __init__(self, medication_name: str):
        super().__init__(
            message=f"'{medication_name}' is already in your medication list."
        )
        self.code = "duplicate_medication"


# ─── RATE LIMITING ────────────────────────────────────────────────────────────

class RateLimitError(PillaraError):
    """
    User has exceeded their request rate limit.
    → HTTP 429 Too Many Requests

    WHY INCLUDE retry_after:
    The HTTP 429 standard includes a Retry-After header.
    This tells the client exactly how many seconds to wait.
    Better UX: "Try again in 45 seconds" vs "You are rate limited."
    """
    def __init__(self, retry_after_seconds: int = 60, limit_type: str = "requests"):
        super().__init__(
            message=f"Too many {limit_type}. Please wait {retry_after_seconds} seconds.",
            code="rate_limit_exceeded",
            status_code=429,
            details={"retry_after_seconds": retry_after_seconds},
        )
        self.retry_after_seconds = retry_after_seconds


class LLMQuotaExceededError(RateLimitError):
    """User has exceeded their daily AI query limit."""
    def __init__(self, resets_in_hours: int = 1):
        super().__init__(
            retry_after_seconds=resets_in_hours * 3600,
            limit_type="AI queries"
        )
        self.code = "llm_quota_exceeded"
        self.message = (
            f"You have reached your AI query limit for today. "
            f"Your limit resets in {resets_in_hours} hour(s). "
            f"Upgrade your plan for unlimited queries."
        )


# ─── SERVICE ERRORS ───────────────────────────────────────────────────────────

class AIServiceError(PillaraError):
    """
    All AI providers failed — service is temporarily unavailable.
    → HTTP 503 Service Unavailable

    WHY 503 (not 500):
    500 = something broke in OUR code (our fault)
    503 = external dependency is unavailable (Groq, Cerebras, etc. are down)
    503 tells the client: this is temporary, try again later.
    """
    def __init__(self, message: str = "AI service is temporarily unavailable"):
        super().__init__(
            message=message,
            code="ai_service_unavailable",
            status_code=503,
        )


class DatabaseError(PillaraError):
    """
    Database operation failed unexpectedly.
    → HTTP 500 Internal Server Error

    WHY NOT EXPOSE DB ERROR DETAILS:
    Database errors often contain table names, column names, query fragments.
    These reveal internal structure that could help an attacker.
    We log the real error internally, return a generic message to the user.
    """
    def __init__(self, operation: str = "database operation"):
        super().__init__(
            message="A server error occurred. Please try again.",
            code="database_error",
            status_code=500,
            details={"operation": operation},
        )


class ExternalAPIError(PillaraError):
    """
    External API (FDA, etc.) returned an error.
    → HTTP 502 Bad Gateway

    WHY 502:
    502 = we received an invalid response from an upstream server.
    Appropriate when we're acting as a gateway to external APIs.
    """
    def __init__(self, service_name: str = "external service"):
        super().__init__(
            message=f"Could not reach {service_name}. Please try again shortly.",
            code="external_api_error",
            status_code=502,
        )


class VoiceProcessingError(PillaraError):
    """Audio transcription or TTS conversion failed."""
    def __init__(self, stage: str = "voice processing"):
        super().__init__(
            message=f"Voice {stage} failed. Please try again or type your question.",
            code="voice_processing_error",
            status_code=500,
        )


class PDFGenerationError(PillaraError):
    """PDF report generation failed."""
    def __init__(self):
        super().__init__(
            message="Could not generate your medication report. Please try again.",
            code="pdf_generation_error",
            status_code=500,
        )