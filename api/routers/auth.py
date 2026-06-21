# api/routers/auth.py
#
# AUTH ENDPOINTS:
# POST /auth/register       — create account
# POST /auth/login          — get tokens
# POST /auth/logout         — revoke current session
# POST /auth/logout-all     — revoke all sessions (all devices)
# POST /auth/refresh        — exchange refresh token for new access token
# POST /auth/password-reset/request  — send reset email
# POST /auth/password-reset/confirm  — complete reset with token
# GET  /auth/me             — get current user info

from fastapi import APIRouter, Depends, Request

from api.dependencies import CurrentUser, DBSession, RedisClient, rate_limit_auth
from core.exceptions import AuthenticationError
from core.security import decode_token
from schemas.all_schemas import (
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    SignupRequest,
    SuccessResponse,
    TokenResponse,
    VerifyEmailRequest,
)
from services.auth_service import AuthService
from monitoring.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=201,
    summary="Create a new Pillara account",
)
async def register(
    signup_data: SignupRequest,
    request: Request,
    db: DBSession,
    redis: RedisClient,
    _: None = Depends(rate_limit_auth),
    # rate_limit_auth runs before this handler — if limit exceeded, request is rejected
) -> TokenResponse:
    """
    Creates a new user account and returns tokens immediately.
    The user is logged in as soon as they register — no separate login step needed.
    """
    service = AuthService(db=db, redis=redis)
    return await service.register_user(
        signup_data=signup_data,
        ip_hash=request.state.ip_hash,
        request_id=request.state.request_id,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Sign in and get access tokens",
)
async def login(
    credentials: LoginRequest,
    request: Request,
    db: DBSession,
    redis: RedisClient,
    _: None = Depends(rate_limit_auth),
) -> TokenResponse:
    """
    Authenticates with email and password.
    Returns access token (30 min) and refresh token (7 days).
    Account locks after 5 failed attempts for 15 minutes.
    """
    service = AuthService(db=db, redis=redis)
    return await service.login(
        email=credentials.email,
        password=credentials.password,
        ip_hash=request.state.ip_hash,
        request_id=request.state.request_id,
    )


@router.post(
    "/logout",
    response_model=SuccessResponse,
    summary="Sign out of current device",
)
async def logout(
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    redis: RedisClient,
) -> SuccessResponse:
    """
    Revokes the current session immediately.
    The access token's JWT may still be cryptographically valid,
    but the session record is deleted from Redis — the token is rejected on next use.
    """
    # Extract jti from the Authorization header token
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()

    try:
        payload = decode_token(token, expected_type="access")
        jti = payload.get("jti", "")
    except Exception:
        jti = ""

    service = AuthService(db=db, redis=redis)
    await service.logout(
        user_id=current_user.id,
        jti=jti,
        request_id=request.state.request_id,
        ip_hash=request.state.ip_hash,
    )
    return SuccessResponse(message="Signed out successfully.")


@router.post(
    "/logout-all",
    response_model=SuccessResponse,
    summary="Sign out of all devices",
)
async def logout_all(
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    redis: RedisClient,
) -> SuccessResponse:
    """
    Revokes ALL sessions for this account.
    Use this if you suspect your account is compromised.
    """
    service = AuthService(db=db, redis=redis)
    count = await service.logout_all(
        user_id=current_user.id,
        request_id=request.state.request_id,
        ip_hash=request.state.ip_hash,
    )
    return SuccessResponse(message=f"Signed out of {count} device(s).")


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Get a new access token using your refresh token",
)
async def refresh_token(
    body: RefreshRequest,
    request: Request,
    db: DBSession,
    redis: RedisClient,
) -> TokenResponse:
    """
    Exchanges a valid refresh token for a new access + refresh token pair.
    The old refresh token is immediately invalidated (token rotation).
    If the refresh token has already been used, all sessions are revoked.
    """
    service = AuthService(db=db, redis=redis)
    return await service.refresh_access_token(
        refresh_token_str=body.refresh_token,
        request_id=request.state.request_id,
    )


@router.post(
    "/password-reset/request",
    response_model=SuccessResponse,
    summary="Request a password reset email",
)
async def request_password_reset(
    body: PasswordResetRequest,
    request: Request,
    db: DBSession,
    _: None = Depends(rate_limit_auth),
) -> SuccessResponse:
    """
    Sends a password reset email if the account exists.
    Always returns success — never reveals whether an email is registered.
    """
    service = AuthService(db=db)
    await service.request_password_reset(
        email=body.email,
        request_id=request.state.request_id,
    )
    return SuccessResponse(
        message="If an account with that email exists, you will receive a reset link shortly."
    )


@router.post(
    "/password-reset/confirm",
    response_model=SuccessResponse,
    summary="Complete password reset with token from email",
)
async def confirm_password_reset(
    body: PasswordResetConfirm,
    request: Request,
    db: DBSession,
    redis: RedisClient,
) -> SuccessResponse:
    """
    Resets the password using the token from the reset email.
    All existing sessions are revoked after a successful reset.
    """
    service = AuthService(db=db, redis=redis)
    await service.reset_password(
        token=body.token,
        new_password=body.new_password,
        request_id=request.state.request_id,
    )
    return SuccessResponse(message="Password updated. Please sign in with your new password.")


@router.post(
    "/verify-email",
    response_model=SuccessResponse,
    summary="Verify email address with token from verification email",
)
async def verify_email(
    body: VerifyEmailRequest,
    request: Request,
    db: DBSession,
    redis: RedisClient,
) -> SuccessResponse:
    """
    Marks the account's email as verified using the token sent at
    registration. Idempotent — clicking an already-used link returns
    success rather than an error.
    """
    service = AuthService(db=db, redis=redis)
    await service.verify_email(
        token=body.token,
        request_id=request.state.request_id,
    )
    return SuccessResponse(message="Email verified. You now have full access to your account.")


@router.get(
    "/me",
    summary="Get current authenticated user info",
)
async def get_me(current_user: CurrentUser) -> dict:
    """
    Returns safe public info about the currently authenticated user.
    Never returns hashed_password, reset tokens, or internal fields.
    """
    return {
        "id": current_user.id,
        "is_verified": current_user.is_verified,
        "subscription_tier": current_user.subscription_tier,
        "onboarding_completed": current_user.onboarding_completed,
        "created_at": current_user.created_at.isoformat(),
        # WHY NOT RETURN EMAIL HERE:
        # Email is PHI. Only return it when the user explicitly needs it
        # (e.g., account settings page — add a dedicated endpoint for that).
        # Minimise PHI surface area in API responses.
    }