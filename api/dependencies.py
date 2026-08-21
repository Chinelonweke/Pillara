# api/dependencies.py
from typing import Annotated, Optional

from fastapi import Depends, Header, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from core.database import get_db
from core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    LLMQuotaExceededError,
    ProfileNotFoundError,
    RateLimitError,
)
from core.redis_client import RateLimiter, SessionManager, get_redis
from core.security import decode_token
from core.config import settings
from models.user import Profile, User
from monitoring.logger import get_logger

logger = get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> User:
    if not credentials:
        raise AuthenticationError("Authentication required. Please sign in.")

    token = credentials.credentials

    try:
        payload = decode_token(token, expected_type="access")
    except Exception:
        raise AuthenticationError("Invalid or expired token. Please sign in again.")

    user_id = payload.get("sub")
    jti = payload.get("jti")

    if not user_id or not jti:
        raise AuthenticationError("Malformed token.")

    session_manager = SessionManager(redis)
    session_valid = await session_manager.verify_session(user_id=user_id, jti=jti)
    if not session_valid:
        raise AuthenticationError("Session expired. Please sign in again.")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise AuthenticationError("Account not found.")
    if not user.is_active:
        raise AuthenticationError("This account has been deactivated.")

    import structlog
    structlog.contextvars.bind_contextvars(user_id=user_id)

    return user


async def get_current_profile(
    profile_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise ProfileNotFoundError(profile_id=profile_id)
    return profile


async def get_profile_from_query(
    profile_id: str = Query(..., description="Profile ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise ProfileNotFoundError(profile_id=profile_id)
    return profile


async def require_verified_email(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_verified:
        raise AuthorizationError(
            "Please verify your email address to access this feature. "
            "Check your inbox for the verification link."
        )
    return current_user


async def rate_limit_api(
    request: Request,
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> None:
    limiter = RateLimiter(redis)
    allowed, count, limit = await limiter.check_rate_limit(
        identifier=current_user.id,
        limit=settings.RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
        namespace="api",
    )
    if not allowed:
        raise RateLimitError(retry_after_seconds=60, limit_type="API requests")


async def rate_limit_auth(
    request: Request,
    redis: Redis = Depends(get_redis),
    x_forwarded_for: Optional[str] = Header(None),
) -> None:
    if x_forwarded_for:
        raw_ip = x_forwarded_for.split(",")[0].strip()
    else:
        raw_ip = request.client.host if request.client else "unknown"

    from core.security import hash_ip_address
    ip_hash = hash_ip_address(raw_ip)

    try:
        body = await request.json()
        email = body.get("email", "unknown")
    except Exception:
        email = "unknown"

    limiter = RateLimiter(redis)
    identifier = limiter.make_auth_identifier(ip_hash=ip_hash, email=email)
    allowed, count, limit = await limiter.check_rate_limit(
        identifier=identifier,
        limit=settings.AUTH_RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
        namespace="auth",
    )
    if not allowed:
        raise RateLimitError(retry_after_seconds=60, limit_type="authentication attempts")


async def rate_limit_llm(
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> None:
    limiter = RateLimiter(redis)

    allowed_hourly, _, _ = await limiter.check_rate_limit(
        identifier=current_user.id,
        limit=settings.LLM_REQUESTS_PER_USER_PER_HOUR,
        window_seconds=3600,
        namespace="llm_hourly",
    )
    if not allowed_hourly:
        raise LLMQuotaExceededError(resets_in_hours=1)

    allowed_daily, _, _ = await limiter.check_rate_limit(
        identifier=current_user.id,
        limit=settings.LLM_REQUESTS_PER_USER_PER_DAY,
        window_seconds=86400,
        namespace="llm_daily",
    )
    if not allowed_daily:
        raise LLMQuotaExceededError(resets_in_hours=24)


CurrentUser = Annotated[User, Depends(get_current_user)]
VerifiedUser = Annotated[User, Depends(require_verified_email)]
CurrentProfile = Annotated[Profile, Depends(get_current_profile)]
DBSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis)]