# models/user.py

import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_token: Mapped[str | None] = mapped_column(String(255), nullable=True)

    password_reset_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_reset_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    refresh_token_jti: Mapped[str | None] = mapped_column(String(36), nullable=True)
    refresh_token_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    subscription_tier: Mapped[str] = mapped_column(String(50), default="free", nullable=False)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Profiles this user CREATED (their own + ones they manage as caregiver)
    profiles: Mapped[list["Profile"]] = relationship(
        "Profile",
        back_populates="user",
        foreign_keys="Profile.user_id",
        cascade="all, delete-orphan"
    )

    # Profiles SHARED WITH this user by others
    access_grants: Mapped[list["ProfileAccess"]] = relationship(
        "ProfileAccess",
        back_populates="granted_to",
        foreign_keys="ProfileAccess.granted_to_user_id"
    )

    def is_locked(self) -> bool:
        from datetime import timezone
        if self.locked_until and self.locked_until > datetime.now(tz=timezone.utc):
            return True
        return False

    def __repr__(self) -> str:
        return f"User(id={self.id!r})"


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))

    # WHO CREATED THIS PROFILE — always set
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # WHO OWNS THIS PROFILE — NULL if unclaimed (patient hasn't joined Pillara yet)
    # When a caregiver creates "Mum's Profile", owner_user_id is NULL until Mum claims it
    owner_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # CLAIM MECHANISM — patient clicks email link to claim ownership
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    claim_token_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # STATUS: "unclaimed" | "active"
    # unclaimed = created by caregiver, patient hasn't claimed yet
    # active    = patient claimed it, or this is user's own profile
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    relationship_to_user: Mapped[str] = mapped_column(String(50), default="self", nullable=False)
    date_of_birth: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    weight_kg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    known_allergies: Mapped[str | None] = mapped_column(Text, nullable=True)
    medical_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="profiles", foreign_keys=[user_id])
    owner: Mapped["User | None"] = relationship("User", foreign_keys=[owner_user_id])
    medications: Mapped[list["Medication"]] = relationship("Medication", back_populates="profile", cascade="all, delete-orphan")
    reminders: Mapped[list["Reminder"]] = relationship("Reminder", back_populates="profile", cascade="all, delete-orphan")
    access_grants: Mapped[list["ProfileAccess"]] = relationship("ProfileAccess", back_populates="profile", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"Profile(id={self.id!r}, status={self.status!r})"

    __table_args__ = (Index("ix_profiles_user_id_primary", "user_id", "is_primary"),)


class ProfileAccess(Base):
    """
    The sharing table. One row = one person's access to one profile.

    ROLES: owner | caregiver | viewer

    INVITE FLOW:
    1. Owner creates invite → row with status='pending', invite_token set
    2. Invitee gets email with link containing token
    3. Invitee logs in, calls accept-invite → status='active', granted_to_user_id set
    4. Profile appears in invitee's dashboard

    REVOCATION:
    Owner revokes → status='revoked' (soft delete, keeps audit trail)
    """
    __tablename__ = "profile_access"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))

    profile_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True)

    # NULL when invite is pending, set when invitee accepts
    granted_to_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)

    # Who sent the invite (for audit trail)
    granted_by_user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")

    # Invite token — single use, cleared after acceptance
    invite_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    invite_token_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invite_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # STATUS: pending | active | revoked
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="access_grants")
    granted_to: Mapped["User | None"] = relationship("User", foreign_keys=[granted_to_user_id], back_populates="access_grants")
    granted_by: Mapped["User"] = relationship("User", foreign_keys=[granted_by_user_id])

    def __repr__(self) -> str:
        return f"ProfileAccess(id={self.id!r}, role={self.role!r}, status={self.status!r})"

    __table_args__ = (
        Index("ix_profile_access_profile_user", "profile_id", "granted_to_user_id"),
        Index("ix_profile_access_user_active", "granted_to_user_id", "status"),
    )


class Medication(Base):
    __tablename__ = "medications"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    generic_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dosage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(100), nullable=True)
    route: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prescribed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fda_application_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fda_data_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="medications")
    reminders: Mapped[list["Reminder"]] = relationship("Reminder", back_populates="medication", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"Medication(id={self.id!r}, profile_id={self.profile_id!r})"


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    medication_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("medications.id", ondelete="CASCADE"), nullable=False)
    reminder_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_rule: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notify_push: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_sms: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_send_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    processing_locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="reminders")
    medication: Mapped["Medication"] = relationship("Medication", back_populates="reminders")

    def __repr__(self) -> str:
        return f"Reminder(id={self.id!r}, profile_id={self.profile_id!r})"

    __table_args__ = (Index("ix_reminders_next_send_active", "next_send_at", "is_active"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    ip_hash: Mapped[str | None] = mapped_column(String(16), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        Index("ix_audit_logs_user_id_created_at", "user_id", "created_at"),
        Index("ix_audit_logs_event_type_created_at", "event_type", "created_at"),
    )

    def __repr__(self) -> str:
        return f"AuditLog(id={self.id!r}, event_type={self.event_type!r})"

class Notification(Base):
    """
    In-app notification log.
    Records every reminder sent and other important events.
    Displayed in the notification bell in the UI.
    """
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())