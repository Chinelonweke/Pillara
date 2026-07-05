# schemas/sharing_schemas.py

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator


class InviteCreateRequest(BaseModel):
    email: EmailStr
    role: str  # "caregiver" or "viewer"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"caregiver", "viewer"}
        if v not in allowed:
            raise ValueError(f"Role must be one of: {allowed}")
        return v


class AcceptInviteRequest(BaseModel):
    invite_token: str


class ClaimProfileRequest(BaseModel):
    claim_token: str


class SendClaimInviteRequest(BaseModel):
    patient_email: EmailStr


class InviteResponse(BaseModel):
    invite_token: str
    invite_email: str
    role: str
    expires_at: datetime
    message: str


class ProfileMemberResponse(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None
    role: str
    status: str
    invited_at: datetime

    model_config = {"from_attributes": True}


class ProfileWithRoleResponse(BaseModel):
    id: str
    name: str
    relationship_to_user: str
    status: str
    is_primary: bool
    role: str
    is_shared_with_me: bool
    created_at: datetime
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None
    known_allergies: Optional[str] = None
    medical_conditions: Optional[str] = None

    model_config = {"from_attributes": True}