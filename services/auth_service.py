import hashlib
from datetime import datetime, timedelta, timezone

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
)
from models.user import User, Profile
from monitoring.audit import AuditEventType, AuditLogger, AuditOutcome
from monitoring.logger import get_logger
from schemas.all_schemas import SignupRequest, TokenResponse

logger = get_logger(__name__)

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
        except IntegrityError as error:
            await self.db.rollback()
            error_str = str(error.orig) if error.orig else str(error)
            if "unique" in error_str.lower() or "23505" in error_str:
                raise EmailAlreadyExistsError()
            raise

        primary_profile = Profile(
            user_id=new_user.id,
            name="Me",
            relationship_to_user="self",
            is_primary=True,
        )
        self.db.add(primary_profile)
        await self.db.flush()

        from services.email_service import send_verification_email
        await send_verification_email(
            to_email=new_user.email,
            verification_token=verification_token,
        )

        access_token = create_access_token(user_id=new_user.id, email=new_user.email)
        refresh_token = create_refresh_token(user_id=new_user.id)

        access_payload = decode_token(access_token, expected_type="access")
        refresh_payload = decode_token(refresh_token, expected_type="refresh")

        new_user.refresh_token_jti = refresh_payload["jti"]
        new_user.refresh_token_expires = datetime.fromtimestamp(
            refresh_payload["exp"], tz=timezone.utc
        )

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

        from monitoring.analytics import track
        track("user_registered", user_id=str(new_user.id))

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
        query = await self.db.execute(select(User).where(User.email == email.lower()))
        user = query.scalar_one_or_none()

        if user is None:
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

        if user.is_locked():
            remaining = (user.locked_until - datetime.now(tz=timezone.utc)).seconds // 60
            raise AuthenticationError(
                f"Account temporarily locked. Try again in {remaining} minutes or reset your password."
            )

        password_correct = verify_password(password, user.hashed_password)

        if not password_correct:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                user.locked_until = datetime.now(tz=timezone.utc) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
                logger.warning("account_locked", user_id=user.id, failed_attempts=user.failed_login_attempts)

            await self.audit.log(
                event_type=AuditEventType.LOGIN_FAILED,
                outcome=AuditOutcome.FAILURE,
                user_id=user.id,
                request_id=request_id,
                ip_hash=ip_hash,
                details={"failed_attempts": user.failed_login_attempts},
            )
            raise AuthenticationError("Invalid email or password")

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = datetime.now(tz=timezone.utc)

        access_token = create_access_token(user_id=user.id, email=user.email)
        refresh_token = create_refresh_token(user_id=user.id)

        access_payload = decode_token(access_token, expected_type="access")
        refresh_payload = decode_token(refresh_token, expected_type="refresh")

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
        if self.redis:
            from core.redis_client import SessionManager
            await SessionManager(self.redis).revoke_session(user_id=user_id, jti=jti)

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
            revoked = await SessionManager(self.redis).revoke_all_sessions(user_id=user_id)

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

        if user.refresh_token_jti != incoming_jti:
            logger.warning("refresh_token_reuse_detected", user_id=user_id, request_id=request_id)
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
            raise AuthenticationError("Security alert: your session was invalidated. Please sign in again.")

        new_access_token = create_access_token(user_id=user.id, email=user.email)
        new_refresh_token = create_refresh_token(user_id=user.id)

        access_payload = decode_token(new_access_token, expected_type="access")
        new_refresh_payload = decode_token(new_refresh_token, expected_type="refresh")

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
            user.password_reset_token_hash = hash_reset_token(raw_token)
            user.password_reset_expires = datetime.now(tz=timezone.utc) + timedelta(
                minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
            )
            from services.email_service import send_password_reset_email
            await send_password_reset_email(to_email=user.email, reset_token=raw_token)
            await self.audit.log(
                event_type=AuditEventType.PASSWORD_RESET,
                outcome=AuditOutcome.SUCCESS,
                user_id=user.id,
                request_id=request_id,
            )

        return True

    async def reset_password(self, token: str, new_password: str, request_id: str = "unknown") -> bool:
        incoming_hash = hash_reset_token(token)

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
        user.failed_login_attempts = 0
        user.locked_until = None

        if self.redis:
            from core.redis_client import SessionManager
            await SessionManager(self.redis).revoke_all_sessions(user_id=user.id)

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
        query = await self.db.execute(
            select(User).where(User.verification_token == token)
        )
        user = query.scalar_one_or_none()

        if not user:
            raise InvalidTokenError("Invalid or expired verification link")

        if user.is_verified:
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