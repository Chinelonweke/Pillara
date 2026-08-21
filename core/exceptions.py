# core/exceptions.py
class PillaraError(Exception):
    def __init__(self, message: str, code: str = "internal_error", status_code: int = 500, details: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message}


class AuthenticationError(PillaraError):
    def __init__(self, message: str = "Authentication required", details: dict = None):
        super().__init__(message=message, code="authentication_required", status_code=401, details=details or {})


class InvalidTokenError(PillaraError):
    def __init__(self, message: str = "Token is invalid or has expired"):
        super().__init__(message=message, code="invalid_token", status_code=401)


class AuthorizationError(PillaraError):
    def __init__(self, message: str = "You do not have permission to do this"):
        super().__init__(message=message, code="permission_denied", status_code=403)


class NotFoundError(PillaraError):
    def __init__(self, resource: str = "Resource", resource_id: str = None):
        message = f"{resource} not found"
        if resource_id:
            message = f"{resource} '{resource_id}' not found"
        super().__init__(message=message, code="not_found", status_code=404, details={"resource": resource, "resource_id": resource_id})


class MedicationNotFoundError(NotFoundError):
    def __init__(self, medication_id: str = None):
        super().__init__(resource="Medication", resource_id=medication_id)
        self.code = "medication_not_found"


class ProfileNotFoundError(NotFoundError):
    def __init__(self, profile_id: str = None):
        super().__init__(resource="Profile", resource_id=profile_id)
        self.code = "profile_not_found"


class ValidationError(PillaraError):
    def __init__(self, message: str, field: str = None):
        super().__init__(message=message, code="validation_error", status_code=422, details={"field": field} if field else {})


class DrugNameInvalidError(ValidationError):
    def __init__(self, drug_name: str):
        super().__init__(
            message=f"'{drug_name}' is not a recognised medication name. Please check the spelling or search for the generic name.",
            field="drug_name",
        )
        self.code = "invalid_drug_name"


class InvalidAudioError(ValidationError):
    def __init__(self, reason: str = "Invalid audio file"):
        super().__init__(message=reason, field="audio")
        self.code = "invalid_audio"


class ConflictError(PillaraError):
    def __init__(self, message: str = "A conflict occurred with existing data"):
        super().__init__(message=message, code="conflict", status_code=409)


class EmailAlreadyExistsError(ConflictError):
    def __init__(self):
        super().__init__(message="An account with this email address already exists. Please sign in or use a different email.")
        self.code = "email_already_exists"


class DuplicateMedicationError(ConflictError):
    def __init__(self, medication_name: str):
        super().__init__(message=f"'{medication_name}' is already in your medication list.")
        self.code = "duplicate_medication"


class RateLimitError(PillaraError):
    def __init__(self, retry_after_seconds: int = 60, limit_type: str = "requests"):
        super().__init__(
            message=f"Too many {limit_type}. Please wait {retry_after_seconds} seconds.",
            code="rate_limit_exceeded",
            status_code=429,
            details={"retry_after_seconds": retry_after_seconds},
        )
        self.retry_after_seconds = retry_after_seconds


class LLMQuotaExceededError(RateLimitError):
    def __init__(self, resets_in_hours: int = 1):
        super().__init__(retry_after_seconds=resets_in_hours * 3600, limit_type="AI queries")
        self.code = "llm_quota_exceeded"
        self.message = f"You have reached your AI query limit. Your limit resets in {resets_in_hours} hour(s)."


class AIServiceError(PillaraError):
    def __init__(self, message: str = "AI service is temporarily unavailable"):
        super().__init__(message=message, code="ai_service_unavailable", status_code=503)


class DatabaseError(PillaraError):
    def __init__(self, operation: str = "database operation"):
        super().__init__(message="A server error occurred. Please try again.", code="database_error", status_code=500, details={"operation": operation})


class ExternalAPIError(PillaraError):
    def __init__(self, service_name: str = "external service"):
        super().__init__(message=f"Could not reach {service_name}. Please try again shortly.", code="external_api_error", status_code=502)


class VoiceProcessingError(PillaraError):
    def __init__(self, stage: str = "voice processing"):
        super().__init__(message=f"Voice {stage} failed. Please try again or type your question.", code="voice_processing_error", status_code=500)


class PDFGenerationError(PillaraError):
    def __init__(self):
        super().__init__(message="Could not generate your medication report. Please try again.", code="pdf_generation_error", status_code=500)