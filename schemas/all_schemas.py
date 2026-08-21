from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, field_validator, model_validator


class SignupRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, password: str) -> str:
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in password):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in password):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in password):
            raise ValueError("Password must contain at least one number")
        special_chars = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        if not any(c in special_chars for c in password):
            raise ValueError("Password must contain at least one special character")
        return password


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, password: str) -> str:
        return SignupRequest.validate_password_strength(password)


class VerifyEmailRequest(BaseModel):
    token: str


class ProfileCreate(BaseModel):
    name: str
    relationship_to_user: str = "self"
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None
    weight_kg: Optional[int] = None
    known_allergies: Optional[str] = None
    medical_conditions: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str) -> str:
        name = name.strip()
        if len(name) < 1:
            raise ValueError("Profile name cannot be empty")
        if len(name) > 100:
            raise ValueError("Profile name is too long (max 100 characters)")
        return name

    @field_validator("relationship_to_user")
    @classmethod
    def validate_relationship(cls, rel: str) -> str:
        allowed = {"self", "parent", "child", "spouse", "sibling", "grandparent", "other"}
        if rel not in allowed:
            raise ValueError(f"relationship_to_user must be one of: {', '.join(sorted(allowed))}")
        return rel


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None
    weight_kg: Optional[int] = None
    known_allergies: Optional[str] = None
    medical_conditions: Optional[str] = None


class ProfileResponse(BaseModel):
    id: str
    name: str
    relationship_to_user: str
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None
    weight_kg: Optional[int] = None
    known_allergies: Optional[str] = None
    medical_conditions: Optional[str] = None
    is_primary: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MedicationCreate(BaseModel):
    name: str
    generic_name: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None
    prescribed_by: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    purpose: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_medication_name(cls, name: str) -> str:
        from core.security import sanitize_medication_name
        sanitized = sanitize_medication_name(name)
        if not sanitized:
            raise ValueError("Medication name cannot be empty or contain invalid characters")
        return sanitized

    @model_validator(mode="after")
    def validate_date_range(self) -> "MedicationCreate":
        if self.start_date and self.end_date:
            if self.end_date <= self.start_date:
                raise ValueError("end_date must be after start_date")
        return self


class MedicationUpdate(BaseModel):
    name: Optional[str] = None
    generic_name: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None
    prescribed_by: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    purpose: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class MedicationResponse(BaseModel):
    id: str
    profile_id: str
    name: str
    generic_name: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    purpose: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class InteractionCheckRequest(BaseModel):
    drug_names: list[str]
    profile_id: Optional[str] = None

    @field_validator("drug_names")
    @classmethod
    def validate_drug_names(cls, drug_names: list) -> list:
        if len(drug_names) < 2:
            raise ValueError("Provide at least 2 drug names to check interactions")
        if len(drug_names) > 10:
            raise ValueError("Can check maximum 10 drugs at once")
        return [name.strip().lower() for name in drug_names]


class InteractionResult(BaseModel):
    drug_a: str
    drug_b: str
    severity: str
    description: str
    action_required: str
    source: Optional[str] = None


class AllergyWarning(BaseModel):
    drug_name: str
    allergen: str
    severity: str
    description: str
    action_required: str


class InteractionCheckResponse(BaseModel):
    drugs_checked: list[str]
    interactions_found: list[InteractionResult]
    allergy_warnings: list[AllergyWarning] = []
    overall_risk: str
    summary: str
    disclaimer: str
    confidence_gate_passed: bool
    provider_used: str
    latency_ms: float


class AIQueryRequest(BaseModel):
    query: str
    profile_id: Optional[str] = None
    conversation_id: Optional[str] = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, query: str) -> str:
        from core.security import sanitize_for_llm
        sanitized = sanitize_for_llm(query)
        if not sanitized:
            raise ValueError("Query cannot be empty")
        return sanitized


class AIQueryResponse(BaseModel):
    response_text: str
    disclaimer: str
    confidence_gate_passed: bool
    fallback_triggered: bool
    query_intent: str
    provider_used: str
    latency_ms: float
    conversation_id: Optional[str] = None


class VoiceInputRequest(BaseModel):
    profile_id: Optional[str] = None
    conversation_id: Optional[str] = None
    language: str = "en"


class VoiceQueryResponse(BaseModel):
    transcription: str
    response_text: str
    audio_url: Optional[str]
    disclaimer: str
    confidence_gate_passed: bool
    provider_used: str
    latency_ms: float


class ReminderCreate(BaseModel):
    medication_id: str
    reminder_time: datetime
    is_recurring: bool = False
    recurrence_rule: Optional[str] = None
    notify_push: bool = True
    notify_email: bool = False
    notify_sms: bool = False

    @model_validator(mode="after")
    def validate_recurrence(self) -> "ReminderCreate":
        if self.is_recurring and not self.recurrence_rule:
            raise ValueError("recurrence_rule is required when is_recurring is True")
        return self


class ReminderResponse(BaseModel):
    id: str
    medication_id: str
    reminder_time: datetime
    is_recurring: bool
    recurrence_rule: Optional[str] = None
    notify_push: bool
    notify_email: bool
    notify_sms: bool
    is_active: bool
    next_send_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReportGenerateRequest(BaseModel):
    profile_id: str
    include_inactive: bool = False


class ReportResponse(BaseModel):
    report_id: str
    download_url: str
    expires_at: datetime
    medication_count: int


class HealthCheckResponse(BaseModel):
    status: str
    version: str
    environment: str
    services: dict[str, Any]


class SuccessResponse(BaseModel):
    success: bool = True
    message: str


class ErrorResponse(BaseModel):
    error: str
    message: str


class PaginationParams(BaseModel):
    page: int = 1
    page_size: int = 20

    @field_validator("page")
    @classmethod
    def validate_page(cls, page: int) -> int:
        if page < 1:
            raise ValueError("page must be >= 1")
        return page

    @field_validator("page_size")
    @classmethod
    def validate_page_size(cls, size: int) -> int:
        if size < 1 or size > 100:
            raise ValueError("page_size must be between 1 and 100")
        return size


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int