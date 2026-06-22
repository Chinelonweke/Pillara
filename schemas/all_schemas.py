# schemas/all_schemas.py
#
# WHY PYDANTIC SCHEMAS:
# SQLAlchemy models define the DATABASE structure (tables, columns).
# Pydantic schemas define the API structure (what goes in and out of endpoints).
# These are DIFFERENT — the API should not expose every database column.
#
# Example: User model has hashed_password. We NEVER include that in an API response.
# Example: User model has is_active. We don't want users setting this themselves.
# Schemas give us precise control over what the API accepts and returns.
#
# NAMING CONVENTION:
# ThingCreate:   data needed to CREATE a thing (POST body)
# ThingUpdate:   data allowed to UPDATE a thing (PATCH/PUT body) — all fields optional
# ThingResponse: data returned ABOUT a thing (GET response) — safe to expose
#
# VALIDATION APPROACH:
# Pydantic validates TYPE (str, int, bool, datetime).
# Our custom validators in this file validate BUSINESS RULES (email format, password strength).
# Custom exceptions in core/exceptions.py handle SEMANTIC errors (duplicate email, not found).

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, field_validator, model_validator


# ─── AUTH SCHEMAS ─────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    """Data required to create a new Pillara account."""

    email: EmailStr
    # EmailStr: Pydantic's email type — validates format (has @, has domain, etc.)
    # Requires the email-validator package

    password: str

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, password: str) -> str:
        """
        WHY VALIDATE PASSWORD HERE (not just length):
        A 8-character password of all letters is cracked in seconds.
        We require a mix of characters to increase entropy.

        RULES:
        - Minimum 8 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one number
        - At least one special character

        WHY THESE SPECIFIC RULES:
        NIST 800-63B (password guidelines) actually recommends
        LENGTH over complexity. But for a healthcare app, we apply
        complexity requirements as an additional layer.
        """
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
    """Credentials for logging in."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """
    Returned on successful login or token refresh.

    WHY BOTH TOKENS IN ONE RESPONSE:
    The client needs both immediately after login.
    access_token: used in Authorization header for all requests
    refresh_token: stored securely, used only to get new access tokens
    """
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # access token lifetime in seconds


class RefreshRequest(BaseModel):
    """Request to exchange a refresh token for a new access token."""
    refresh_token: str


class PasswordResetRequest(BaseModel):
    """Request to send a password reset email."""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Complete a password reset with the token from the email."""
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, password: str) -> str:
        # Reuse the same validation logic
        return SignupRequest.validate_password_strength(password)


class VerifyEmailRequest(BaseModel):
    """Confirm an email address using the token from the verification email."""
    token: str


# ─── PROFILE SCHEMAS ──────────────────────────────────────────────────────────

class ProfileCreate(BaseModel):
    """Data to create a new profile (person being managed)."""
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
    """
    All fields optional — PATCH semantics.
    Only update what the user provides; keep existing values for everything else.
    """
    name: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None
    weight_kg: Optional[int] = None
    known_allergies: Optional[str] = None
    medical_conditions: Optional[str] = None


class ProfileResponse(BaseModel):
    """Safe profile data to return in API responses."""
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

    class Config:
        from_attributes = True
        # from_attributes=True: allows creating this schema from a SQLAlchemy model
        # Usage: ProfileResponse.model_validate(profile_orm_object)
        # Pydantic reads the attributes (profile.name) and populates the schema


# ─── MEDICATION SCHEMAS ───────────────────────────────────────────────────────

class MedicationCreate(BaseModel):
    """Data to add a new medication to a profile."""
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
        """
        WHY model_validator (not field_validator):
        This validation needs TWO fields simultaneously — start_date and end_date.
        field_validator only sees one field at a time.
        model_validator sees the complete model after all field validators run.
        """
        if self.start_date and self.end_date:
            if self.end_date <= self.start_date:
                raise ValueError("end_date must be after start_date")
        return self


class MedicationUpdate(BaseModel):
    """All fields optional — PATCH semantics for medication updates."""
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
    """Medication data safe to return in responses."""
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

    class Config:
        from_attributes = True


# ─── INTERACTION SCHEMAS ──────────────────────────────────────────────────────

class InteractionCheckRequest(BaseModel):
    """Request to check drug interactions."""
    drug_names: list[str]
    # List of drug names to check against each other
    profile_id: Optional[str] = None
    # Optional: if provided, we also check against profile's current medications

    @field_validator("drug_names")
    @classmethod
    def validate_drug_names(cls, drug_names: list) -> list:
        if len(drug_names) < 2:
            raise ValueError("Provide at least 2 drug names to check interactions")
        if len(drug_names) > 10:
            raise ValueError("Can check maximum 10 drugs at once")
        return [name.strip().lower() for name in drug_names]


class InteractionResult(BaseModel):
    """Result of one drug-drug interaction check."""
    drug_a: str
    drug_b: str
    severity: str                 # "high", "moderate", "low", "none", "unknown"
    description: str              # plain language explanation
    action_required: str          # what the user should do
    source: Optional[str] = None  # where this information came from


class AllergyWarning(BaseModel):
    """
    A deterministic allergy cross-reactivity warning.

    WHY SEPARATE FROM InteractionResult:
    Drug-drug interactions are probabilistic — severity varies, context
    matters, the LLM/RAG pipeline is the right tool. Allergy cross-
    reactivity warnings for known drug classes are deterministic — if a
    patient has a documented Penicillin allergy and is checking amoxicillin
    (a penicillin-class antibiotic), this is always a high-severity warning,
    with no LLM judgment required. Keeping these separate in the response
    means clients can always trust that allergy_warnings are structurally
    reliable, not probabilistic, and can render them differently (e.g.
    always show a red banner, regardless of overall_risk).
    """
    drug_name: str           # the drug being checked
    allergen: str            # the documented allergy it conflicts with
    severity: str            # always "high" for known cross-reactivity
    description: str         # plain language explanation
    action_required: str     # what the user should do


class InteractionCheckResponse(BaseModel):
    """Complete response from an interaction check."""
    drugs_checked: list[str]
    interactions_found: list[InteractionResult]
    allergy_warnings: list[AllergyWarning] = []
    # WHY DEFAULT EMPTY LIST (not Optional):
    # The frontend should always be able to iterate allergy_warnings without
    # null-checking — an empty list is unambiguous ("no warnings found"),
    # while None could mean "not checked" vs "checked and found nothing."
    # For a safety feature, that distinction matters: clients deserve to know
    # the check ran and found nothing, not just that no data was returned.
    overall_risk: str             # "high", "moderate", "low", "none"
    summary: str                  # one-sentence summary for the user
    disclaimer: str
    confidence_gate_passed: bool  # True = answered from verified data
    provider_used: str
    latency_ms: float


# ─── AI CHAT SCHEMAS ──────────────────────────────────────────────────────────

class AIQueryRequest(BaseModel):
    """A text query to the AI medication assistant."""
    query: str
    profile_id: Optional[str] = None
    conversation_id: Optional[str] = None
    # If provided, the AI uses conversation history for context

    @field_validator("query")
    @classmethod
    def validate_query(cls, query: str) -> str:
        from core.security import sanitize_for_llm
        sanitized = sanitize_for_llm(query)
        if not sanitized:
            raise ValueError("Query cannot be empty")
        return sanitized


class AIQueryResponse(BaseModel):
    """Response from the AI medication assistant."""
    response_text: str
    disclaimer: str
    confidence_gate_passed: bool
    fallback_triggered: bool
    query_intent: str
    provider_used: str
    latency_ms: float
    conversation_id: Optional[str] = None


class VoiceInputRequest(BaseModel):
    """
    Voice query — the audio is uploaded as a multipart file.
    This schema handles the non-file metadata.
    """
    profile_id: Optional[str] = None
    conversation_id: Optional[str] = None
    language: str = "en"
    # Language code for Whisper transcription
    # "en", "yo" (Yoruba), "ha" (Hausa), "ig" (Igbo), "pcm" (Nigerian Pidgin)


class VoiceQueryResponse(BaseModel):
    """Response to a voice query — includes both text and audio."""
    transcription: str         # what Whisper heard the user say
    response_text: str         # the AI's text response
    audio_url: Optional[str]   # URL to the TTS audio file
    disclaimer: str
    confidence_gate_passed: bool
    provider_used: str
    latency_ms: float


# ─── REMINDER SCHEMAS ─────────────────────────────────────────────────────────

class ReminderCreate(BaseModel):
    """Data to create a medication reminder."""
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
    """Reminder data for API responses."""
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

    class Config:
        from_attributes = True


# ─── REPORT SCHEMAS ───────────────────────────────────────────────────────────

class ReportGenerateRequest(BaseModel):
    """Request to generate a medication report PDF."""
    profile_id: str
    include_inactive: bool = False
    # If True, include medications with is_active=False (historical)


class ReportResponse(BaseModel):
    """Response confirming report generation."""
    report_id: str
    download_url: str
    expires_at: datetime
    medication_count: int


# ─── HEALTH CHECK SCHEMAS ─────────────────────────────────────────────────────

class HealthCheckResponse(BaseModel):
    """Response from the /health endpoint."""
    status: str           # "healthy" or "degraded"
    version: str
    environment: str
    services: dict[str, Any]
    # services contains status of: database, redis, chromadb, llm_providers


# ─── GENERIC RESPONSE SCHEMAS ─────────────────────────────────────────────────

class SuccessResponse(BaseModel):
    """Generic success response for operations that don't return data."""
    success: bool = True
    message: str


class ErrorResponse(BaseModel):
    """
    Standard error response shape.
    All API errors return this structure.

    WHY CONSISTENT ERROR SHAPE:
    The frontend can always expect the same structure on error.
    error.code lets the frontend handle specific errors (show different messages).
    error.message is human-readable for display.
    """
    error: str    # machine-readable error code
    message: str  # human-readable message


# ─── PAGINATION ───────────────────────────────────────────────────────────────

class PaginationParams(BaseModel):
    """Standard pagination parameters for list endpoints."""
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
    """Wrapper for paginated list responses."""
    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int