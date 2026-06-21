# services/auth_service.py
# SECURITY UPDATES FROM AUDIT:
# 1. UniqueViolationError catch — handles registration race condition correctly
# 2. Password reset token stored as SHA256 hash (never plaintext)
# 3. Refresh token jti stored in database — enables true server-side revocation
# 4. Account lockout after 5 failed login attempts (15-minute lockout)
# 5. Failed attempt counter resets on successful login
# 6. Refresh token reuse detection — if jti doesn't match, revoke everything

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.config import settings
from core.exceptions import (
    AuthenticationError,
    EmailAlreadyExistsError,
    InvalidTokenError,
)
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_secure_token,
    hash_password,
    hash_reset_token,
    verify_password,
    verify_reset_token,
)
from models.user import User, Profile
from monitoring.audit import AuditEventType, AuditLogger, AuditOutcome
from monitoring.logger import get_logger
from schemas.all_schemas import SignupRequest, TokenResponse

logger = get_logger(__name__)

# Account lockout settings
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15


class AuthService:

    def __init__(self, db: AsyncSession, redis=None):
        self.db = db
        self.redis = redis
        self.audit = AuditLogger(db=db)

    async def register_user(
        self,
        signup_data: SignupRequest,
        ip_hash: str = "unknown",
        request_id: str = "unknown",
    ) -> TokenResponse:
        """
        Registers a new user.

        RACE CONDITION FIX:
        We no longer do SELECT-then-INSERT (which has a race window).
        Instead we INSERT directly and catch the UniqueViolationError from PostgreSQL.
        The database's UNIQUE constraint is the true enforcement — not our SELECT check.

        This is the only correct way to handle concurrent registrations.
        SELECT + INSERT = two operations = race window.
        INSERT + catch unique violation = one atomic operation = no race.
        """
        password_hash = hash_password(signup_data.password)
        verification_token = generate_secure_token(32)

        new_user = User(
            email=signup_data.email.lower(),
            hashed_password=password_hash,
            is_active=True,
            is_verified=False,
            verification_token=verification_token,
        )

        try:
            self.db.add(new_user)
            await self.db.flush()
            # flush() sends the INSERT to PostgreSQL within our transaction.
            # If the email already exists, PostgreSQL raises IntegrityError here.
            # We catch it below and convert to EmailAlreadyExistsError.

        except IntegrityError as error:
            # IntegrityError wraps PostgreSQL's UniqueViolationError (code 23505)
            await self.db.rollback()
            error_str = str(error.orig) if error.orig else str(error)

            if "unique" in error_str.lower() or "23505" in error_str:
                logger.warning("registration_race_condition_caught", request_id=request_id)
                raise EmailAlreadyExistsError()

            # Some other integrity violation — re-raise as-is
            raise

        # Create the primary profile
        primary_profile = Profile(
            user_id=new_user.id,
            name="Me",
            relationship_to_user="self",
            is_primary=True,
        )
        self.db.add(primary_profile)
        await self.db.flush()

        # Send verification email.
        # WHY HERE: new_user.id and verification_token both exist now, the
        # INSERT has succeeded (flush() above would have raised otherwise).
        # WHY NOT AWAITED INTO THE TRANSACTION'S SUCCESS: send_verification_email()
        # never raises (see services/email_service.py) — if Resend is down,
        # we log it and continue. The user account is real either way; a
        # failed send just means they'll need a "resend verification email"
        # action later, not that registration itself should fail.
        from services.email_service import send_verification_email
        await send_verification_email(
            to_email=new_user.email,
            verification_token=verification_token,
        )

        # Issue tokens
        access_token = create_access_token(user_id=new_user.id, email=new_user.email)
        refresh_token = create_refresh_token(user_id=new_user.id)

        access_payload = decode_token(access_token, expected_type="access")
        refresh_payload = decode_token(refresh_token, expected_type="refresh")

        # SECURITY FIX: Store refresh token jti in database for server-side revocation.
        # Without this, a stolen refresh token is valid for its full 7-day lifetime
        # even after the user logs out. With this, logout sets refresh_token_jti=None
        # and the token is immediately unusable.
        new_user.refresh_token_jti = refresh_payload["jti"]
        new_user.refresh_token_expires = datetime.fromtimestamp(
            refresh_payload["exp"], tz=timezone.utc
        )

        # Store access token session in Redis
        if self.redis:
            from core.redis_client import SessionManager
            session_manager = SessionManager(self.redis)
            await session_manager.create_session(
                user_id=new_user.id,
                jti=access_payload["jti"],
                ip_hash=ip_hash,
            )

        await self.audit.log(
            event_type=AuditEventType.USER_REGISTERED,
            outcome=AuditOutcome.SUCCESS,
            user_id=new_user.id,
            request_id=request_id,
            ip_hash=ip_hash,
        )

        logger.info("user_registered", user_id=new_user.id, request_id=request_id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def login(
        self,
        email: str,
        password: str,
        ip_hash: str = "unknown",
        request_id: str = "unknown",
    ) -> TokenResponse:
        """
        Authenticates a user.

        SECURITY FEATURES:
        1. Timing attack prevention — always run bcrypt even for non-existent users
        2. Account lockout — after 5 failures, lock for 15 minutes
        3. Failed attempt counter — increments on each bad password
        4. Counter reset — clears on successful login
        """
        query = await self.db.execute(select(User).where(User.email == email.lower()))
        user = query.scalar_one_or_none()

        if user is None:
            # Timing attack prevention: run bcrypt even when user doesn't exist
            verify_password(password, "$2b$12$fakehashfakehashfakehashfakehashfakehashfakeha")
            await self.audit.log(
                event_type=AuditEventType.LOGIN_FAILED,
                outcome=AuditOutcome.FAILURE,
                request_id=request_id,
                ip_hash=ip_hash,
                details={"reason": "user_not_found"},
            )
            raise AuthenticationError("Invalid email or password")

        if not user.is_active:
            raise AuthenticationError("This account has been deactivated.")

        # SECURITY FIX: Check account lockout BEFORE running bcrypt.
        # This prevents an attacker from using lockout as a timing oracle.
        if user.is_locked():
            remaining = (user.locked_until - datetime.now(tz=timezone.utc)).seconds // 60
            raise AuthenticationError(
                f"Account temporarily locked due to too many failed attempts. "
                f"Try again in {remaining} minutes or reset your password."
            )

        password_correct = verify_password(password, user.hashed_password)

        if not password_correct:
            # SECURITY FIX: Increment failed attempt counter
            user.failed_login_attempts += 1

            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                # Lock the account
                user.locked_until = datetime.now(tz=timezone.utc) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
                logger.warning(
                    "account_locked",
                    user_id=user.id,
                    failed_attempts=user.failed_login_attempts,
                )

            await self.audit.log(
                event_type=AuditEventType.LOGIN_FAILED,
                outcome=AuditOutcome.FAILURE,
                user_id=user.id,
                request_id=request_id,
                ip_hash=ip_hash,
                details={"failed_attempts": user.failed_login_attempts},
            )
            raise AuthenticationError("Invalid email or password")

        # Successful login — reset lockout state
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = datetime.now(tz=timezone.utc)

        access_token = create_access_token(user_id=user.id, email=user.email)
        refresh_token = create_refresh_token(user_id=user.id)

        access_payload = decode_token(access_token, expected_type="access")
        refresh_payload = decode_token(refresh_token, expected_type="refresh")

        # SECURITY FIX: Rotate refresh token in database
        user.refresh_token_jti = refresh_payload["jti"]
        user.refresh_token_expires = datetime.fromtimestamp(refresh_payload["exp"], tz=timezone.utc)

        if self.redis:
            from core.redis_client import SessionManager
            session_manager = SessionManager(self.redis)
            await session_manager.create_session(
                user_id=user.id,
                jti=access_payload["jti"],
                ip_hash=ip_hash,
            )

        await self.audit.log(
            event_type=AuditEventType.USER_LOGIN,
            outcome=AuditOutcome.SUCCESS,
            user_id=user.id,
            request_id=request_id,
            ip_hash=ip_hash,
        )

        logger.info("user_login_success", user_id=user.id, request_id=request_id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def logout(self, user_id: str, jti: str, request_id: str = "unknown", ip_hash: str = "unknown") -> bool:
        # Revoke access token session in Redis
        if self.redis:
            from core.redis_client import SessionManager
            session_manager = SessionManager(self.redis)
            await session_manager.revoke_session(user_id=user_id, jti=jti)

        # SECURITY FIX: Clear refresh token from database on logout
        # This means the refresh token is immediately unusable after logout.
        query = await self.db.execute(select(User).where(User.id == user_id))
        user = query.scalar_one_or_none()
        if user:
            user.refresh_token_jti = None
            user.refresh_token_expires = None

        await self.audit.log(
            event_type=AuditEventType.USER_LOGOUT,
            outcome=AuditOutcome.SUCCESS,
            user_id=user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return True

    async def logout_all(self, user_id: str, request_id: str = "unknown", ip_hash: str = "unknown") -> int:
        revoked = 0
        if self.redis:
            from core.redis_client import SessionManager
            session_manager = SessionManager(self.redis)
            revoked = await session_manager.revoke_all_sessions(user_id=user_id)

        # Clear refresh token in database
        query = await self.db.execute(select(User).where(User.id == user_id))
        user = query.scalar_one_or_none()
        if user:
            user.refresh_token_jti = None
            user.refresh_token_expires = None

        await self.audit.log(
            event_type=AuditEventType.USER_LOGOUT_ALL,
            outcome=AuditOutcome.SUCCESS,
            user_id=user_id,
            request_id=request_id,
            ip_hash=ip_hash,
            details={"sessions_revoked": revoked},
        )
        return revoked

    async def refresh_access_token(self, refresh_token_str: str, request_id: str = "unknown") -> TokenResponse:
        """
        SECURITY FIX — REFRESH TOKEN REUSE DETECTION:
        When a refresh token is used, we check the jti matches what's stored in DB.
        If it doesn't match, it means either:
        a) The token was already used (rotation issued a new one), OR
        b) An attacker is using a stolen old token

        In either case: revoke EVERYTHING and force re-login.
        This is called "refresh token reuse detection" — industry standard pattern.
        """
        try:
            payload = decode_token(refresh_token_str, expected_type="refresh")
        except InvalidTokenError:
            raise AuthenticationError("Invalid or expired refresh token")

        user_id = payload["sub"]
        incoming_jti = payload["jti"]

        query = await self.db.execute(select(User).where(User.id == user_id))
        user = query.scalar_one_or_none()

        if not user or not user.is_active:
            raise AuthenticationError("Account not found or deactivated")

        # SECURITY: Check that this refresh token jti matches what we have stored
        if user.refresh_token_jti != incoming_jti:
            # Token reuse detected — possible token theft
            # Revoke ALL sessions as a security precaution
            logger.warning(
                "refresh_token_reuse_detected",
                user_id=user_id,
                request_id=request_id,
            )
            # Clear everything — force re-login on all devices
            user.refresh_token_jti = None
            user.refresh_token_expires = None
            if self.redis:
                from core.redis_client import SessionManager
                await SessionManager(self.redis).revoke_all_sessions(user_id=user_id)

            await self.audit.log(
                event_type=AuditEventType.USER_LOGOUT_ALL,
                outcome=AuditOutcome.DENIED,
                user_id=user_id,
                request_id=request_id,
                details={"reason": "refresh_token_reuse_detected"},
            )
            raise AuthenticationError(
                "Security alert: your session was invalidated. Please sign in again."
            )

        # Valid refresh — issue new tokens
        new_access_token = create_access_token(user_id=user.id, email=user.email)
        new_refresh_token = create_refresh_token(user_id=user.id)

        access_payload = decode_token(new_access_token, expected_type="access")
        new_refresh_payload = decode_token(new_refresh_token, expected_type="refresh")

        # Rotate: store new refresh jti, invalidate old one
        user.refresh_token_jti = new_refresh_payload["jti"]
        user.refresh_token_expires = datetime.fromtimestamp(new_refresh_payload["exp"], tz=timezone.utc)

        if self.redis:
            from core.redis_client import SessionManager
            session_manager = SessionManager(self.redis)
            await session_manager.revoke_session(user_id=user_id, jti=payload.get("access_jti", ""))
            await session_manager.create_session(user_id=user_id, jti=access_payload["jti"])

        await self.audit.log(
            event_type=AuditEventType.TOKEN_REFRESHED,
            outcome=AuditOutcome.SUCCESS,
            user_id=user_id,
            request_id=request_id,
        )

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def request_password_reset(self, email: str, request_id: str = "unknown") -> bool:
        query = await self.db.execute(select(User).where(User.email == email.lower()))
        user = query.scalar_one_or_none()

        if user and user.is_active:
            raw_token = generate_secure_token(32)

            # SECURITY FIX: Store the HASH of the token, not the token itself.
            # If the database is breached, attackers get hashes — useless without the raw token.
            user.password_reset_token_hash = hash_reset_token(raw_token)
            user.password_reset_expires = datetime.now(tz=timezone.utc) + timedelta(
                minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
            )

            # TODO: Queue email: send raw_token in the reset link URL
            # The raw_token goes in the email. The hash stays in the DB.
            # await send_password_reset_email.enqueue(email=user.email, token=raw_token)

            await self.audit.log(
                event_type=AuditEventType.PASSWORD_RESET,
                outcome=AuditOutcome.SUCCESS,
                user_id=user.id,
                request_id=request_id,
            )

        # Always return True — don't reveal whether the email is registered
        return True

    async def reset_password(self, token: str, new_password: str, request_id: str = "unknown") -> bool:
        """
        SECURITY FIX: Compare hash of incoming token against stored hash.
        Never compare raw tokens — that would require storing them in plaintext.
        """
        incoming_hash = hash_reset_token(token)

        # Find user by the HASH of the token (never by raw token)
        query = await self.db.execute(
            select(User).where(User.password_reset_token_hash == incoming_hash)
        )
        user = query.scalar_one_or_none()

        if not user:
            raise InvalidTokenError("Invalid or expired password reset link")

        if not user.password_reset_expires or \
           user.password_reset_expires < datetime.now(tz=timezone.utc):
            raise InvalidTokenError("Password reset link has expired. Please request a new one.")

        user.hashed_password = hash_password(new_password)
        user.password_reset_token_hash = None
        user.password_reset_expires = None
        # Reset lockout on password change — they proved identity via email
        user.failed_login_attempts = 0
        user.locked_until = None

        if self.redis:
            from core.redis_client import SessionManager
            await SessionManager(self.redis).revoke_all_sessions(user_id=user.id)

        # Also clear refresh token
        user.refresh_token_jti = None
        user.refresh_token_expires = None

        await self.audit.log(
            event_type=AuditEventType.PASSWORD_CHANGED,
            outcome=AuditOutcome.SUCCESS,
            user_id=user.id,
            request_id=request_id,
        )
        return True

    async def verify_email(self, token: str, request_id: str = "unknown") -> bool:
        """
        Marks a user's email as verified using the token from the
        verification email.

        WHY THE TOKEN IS COMPARED DIRECTLY (not hashed, unlike reset_password):
        verification_token is stored in plaintext in the users table (see
        register_user() above). This is a deliberate, lower-stakes tradeoff
        from password reset tokens: a leaked verification token only lets
        someone mark an email "verified" early — it doesn't grant login
        access or account control the way a leaked password reset token
        would. Hashing it would be defense-in-depth, but isn't required
        for the actual threat model here.
        """
        query = await self.db.execute(
            select(User).where(User.verification_token == token)
        )
        user = query.scalar_one_or_none()

        if not user:
            raise InvalidTokenError("Invalid or expired verification link")

        if user.is_verified:
            # Already verified — clicking an old link twice shouldn't error,
            # just confirm it's done. Idempotent on purpose.
            return True

        user.is_verified = True
        user.verification_token = None

        await self.audit.log(
            event_type=AuditEventType.EMAIL_VERIFIED,
            outcome=AuditOutcome.SUCCESS,
            user_id=user.id,
            request_id=request_id,
        )
        return True