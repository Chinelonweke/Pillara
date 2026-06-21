# api/dependencies.py
#
# FastAPI dependencies are injected into route handlers automatically.
# They run before the route handler and can short-circuit with an exception.
#
# DEPENDENCIES IN THIS FILE:
# get_current_user       — validates JWT, checks Redis session, returns User
# get_current_profile    — validates profile belongs to current user (IDOR guard)
# require_verified_email — blocks unverified users from sensitive endpoints
# rate_limit_auth        — strict rate limit for login/register (by ip+email)
# rate_limit_api         — standard rate limit for API calls (by user_id)
# rate_limit_llm         — LLM-specific quota (by user_id, daily cap)
# get_db                 — re-exported from core.database for convenience
# get_redis              — re-exported from core.redis_client for convenience
#
# IDOR PROTECTION PHILOSOPHY:
# get_current_profile is the single enforcement point for profile ownership.
# Every route that touches a profile uses this dependency.
# If we ever need to change the ownership check, we change it in ONE place.
# This is the only correct architecture for IDOR prevention in a multi-profile app.

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

# HTTP Bearer token scheme — reads the Authorization: Bearer <token> header
bearer_scheme = HTTPBearer(auto_error=False)
# auto_error=False: don't raise automatically — we raise our own cleaner error


# ─── AUTHENTICATION ───────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> User:
    """
    Validates the JWT access token and returns the authenticated User.

    SECURITY CHECKS (in order):
    1. Token present in Authorization header
    2. Token signature is valid (JWT verification)
    3. Token type is "access" (not refresh or reset)
    4. Token not expired (JWT expiry claim)
    5. Session still exists in Redis (not logged out)
    6. User exists in database and is active

    WHY ALL SIX CHECKS:
    JWT alone (checks 1-4) cannot be revoked before expiry.
    Redis session (check 5) is how logout actually works.
    Database check (check 6) catches deactivated accounts.
    All six together = real authentication, not just "the token looks valid."

    USAGE IN ROUTES:
        async def my_route(user: User = Depends(get_current_user)):
            # user is the authenticated User object
    """
    if not credentials:
        raise AuthenticationError("Authentication required. Please sign in.")

    token = credentials.credentials

    # Decode and verify JWT
    try:
        payload = decode_token(token, expected_type="access")
    except Exception:
        raise AuthenticationError("Invalid or expired token. Please sign in again.")

    user_id = payload.get("sub")
    jti = payload.get("jti")

    if not user_id or not jti:
        raise AuthenticationError("Malformed token.")

    # Check Redis session — this is what makes logout work
    session_manager = SessionManager(redis)
    session_valid = await session_manager.verify_session(user_id=user_id, jti=jti)
    if not session_valid:
        raise AuthenticationError("Session expired. Please sign in again.")

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise AuthenticationError("Account not found.")

    if not user.is_active:
        raise AuthenticationError("This account has been deactivated.")

    # Bind user_id to structlog context — appears in all subsequent log lines
    import structlog
    structlog.contextvars.bind_contextvars(user_id=user_id)

    return user


# ─── PROFILE OWNERSHIP (IDOR PROTECTION) ─────────────────────────────────────

async def get_current_profile(
    profile_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    """
    Fetches a profile AND verifies it belongs to the current user.

    THIS IS THE IDOR GUARD FOR ALL PROFILE-SCOPED OPERATIONS.

    WHY THIS EXISTS AS A DEPENDENCY (not inline in each route):
    If we checked ownership inline in every route, we'd need to remember
    to do it every single time. One forgotten check = IDOR vulnerability.

    As a dependency, the route CANNOT access a profile without this check.
    Ownership enforcement is structural, not optional.

    WHAT THIS PREVENTS:
    User A has profile ID "550e8400-abc"
    User B sends GET /api/v1/medications?profile_id=550e8400-abc
    Without this guard: User B sees User A's medications.
    With this guard: User B gets 404 (we never confirm the profile exists for them)

    WHY 404 (not 403):
    403 = "you can't access this" — confirms the resource exists.
    404 = "not found" — reveals nothing about whether the profile exists.
    Attackers cannot enumerate profiles by probing for 403 vs 404.

    USAGE IN ROUTES:
        async def my_route(
            profile: Profile = Depends(get_current_profile),
        ):
            # profile is verified to belong to the current user
    """
    result = await db.execute(
        select(Profile).where(
            Profile.id == profile_id,
            Profile.user_id == current_user.id,
            # BOTH conditions must be true.
            # profile_id alone is not enough — it must belong to THIS user.
        )
    )
    profile = result.scalar_one_or_none()

    if not profile:
        # 404 not 403 — don't confirm whether the profile exists at all
        raise ProfileNotFoundError(profile_id=profile_id)

    return profile


async def get_profile_from_query(
    profile_id: str = Query(..., description="Profile ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    """
    Same as get_current_profile but reads profile_id from query params.
    Used for GET endpoints: GET /medications?profile_id=xxx
    """
    result = await db.execute(
        select(Profile).where(
            Profile.id == profile_id,
            Profile.user_id == current_user.id,
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise ProfileNotFoundError(profile_id=profile_id)
    return profile


# ─── EMAIL VERIFICATION ───────────────────────────────────────────────────────

async def require_verified_email(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Blocks access to sensitive endpoints until the user verifies their email.

    WHY REQUIRE VERIFICATION:
    Unverified emails mean anyone can sign up with someone else's email address
    and immediately access sensitive features. Email verification proves
    the user controls the email address they registered with.

    Apply this to: medication management, AI queries, profile medical data.
    Do NOT apply to: profile setup, email resend, account settings.
    """
    if not current_user.is_verified:
        raise AuthorizationError(
            "Please verify your email address to access this feature. "
            "Check your inbox for the verification link."
        )
    return current_user


# ─── RATE LIMITING ────────────────────────────────────────────────────────────

async def rate_limit_api(
    request: Request,
    # WHY request: Request (typed) MATTERS HERE, NOT JUST AS STYLE:
    # FastAPI builds the OpenAPI schema by inspecting the full dependency
    # tree, not just the route function. An untyped `request` parameter in
    # a dependency (like this one) gets misread as a generic required QUERY
    # parameter — it shows up in Swagger UI as a phantom field the API
    # never actually expects, breaking "Try it out" for every endpoint that
    # uses this dependency. Typing it as Request tells FastAPI this is the
    # special internal request object, correctly excluding it from the
    # public API schema.
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> None:
    """
    Standard API rate limit — keyed on user_id.

    WHY user_id (not IP):
    IPv6 gives attackers 2^64 addresses — IP-based limiting is trivially bypassed.
    user_id is the same regardless of which IP, VPN, or device the user connects from.
    This is IPv6-proof rate limiting.

    Limit: 60 requests per minute per user.
    """
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
    # See the matching comment on rate_limit_api above — same root cause,
    # same fix. This is the dependency actually used by /auth/register,
    # /auth/login, and /auth/password-reset/request, which is why all
    # three of those endpoints showed the same phantom "request" query
    # parameter in Swagger UI before this fix.
    redis: Redis = Depends(get_redis),
    x_forwarded_for: Optional[str] = Header(None),
) -> None:
    """
    Strict rate limit for unauthenticated auth endpoints (login, register, reset).

    WHY COMBINED ip+email KEY:
    IP-only: attacker rotates IPs and bypasses per-IP limit
    Email-only: attacker tries one email from millions of IPs
    Combined: attacker must rotate BOTH simultaneously — much harder

    Limit: 5 requests per minute per ip+email combination.
    This allows legitimate users to mistype their password a few times
    while blocking automated credential stuffing attacks.
    """
    # Get client IP
    if x_forwarded_for:
        raw_ip = x_forwarded_for.split(",")[0].strip()
    else:
        raw_ip = request.client.host if request.client else "unknown"

    from core.security import hash_ip_address
    ip_hash = hash_ip_address(raw_ip)

    # Try to get email from request body for combined key
    # We read the body carefully — middleware may have already consumed it
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
        raise RateLimitError(
            retry_after_seconds=60,
            limit_type="authentication attempts"
        )


async def rate_limit_llm(
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> None:
    """
    LLM-specific rate limit — daily quota per user.

    WHY A SEPARATE LLM LIMIT:
    LLM calls are expensive (latency, compute, provider costs).
    A user running automated scripts could exhaust all provider quotas.
    We enforce a daily limit separate from the general API rate limit.

    Free tier: 20 LLM requests per hour, 100 per day.
    Future: premium tiers get higher limits.

    WHY PER HOUR AND PER DAY:
    Per-hour prevents burst abuse (hammering in a short window).
    Per-day prevents sustained abuse across the whole day.
    """
    limiter = RateLimiter(redis)

    # Hourly check
    allowed_hourly, count_h, limit_h = await limiter.check_rate_limit(
        identifier=current_user.id,
        limit=settings.LLM_REQUESTS_PER_USER_PER_HOUR,
        window_seconds=3600,
        namespace="llm_hourly",
    )
    if not allowed_hourly:
        raise LLMQuotaExceededError(resets_in_hours=1)

    # Daily check
    allowed_daily, count_d, limit_d = await limiter.check_rate_limit(
        identifier=current_user.id,
        limit=settings.LLM_REQUESTS_PER_USER_PER_DAY,
        window_seconds=86400,
        namespace="llm_daily",
    )
    if not allowed_daily:
        raise LLMQuotaExceededError(resets_in_hours=24)


# ─── TYPE ALIASES ─────────────────────────────────────────────────────────────
# These make route signatures cleaner and self-documenting.
# Instead of: current_user: User = Depends(get_current_user)
# You write:  current_user: CurrentUser
# Same result — FastAPI resolves the dependency automatically.

CurrentUser = Annotated[User, Depends(get_current_user)]
VerifiedUser = Annotated[User, Depends(require_verified_email)]
CurrentProfile = Annotated[Profile, Depends(get_current_profile)]
DBSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis)]