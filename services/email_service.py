# services/email_service.py
#
# WHY A SEPARATE MODULE (not inline in auth_service.py):
# Email sending is a distinct concern from authentication business logic.
# Keeping it separate means: (1) auth_service.py stays focused on auth,
# (2) we can reuse send_verification_email() and friends from anywhere
# (e.g. a future "resend verification email" endpoint), (3) it's the one
# place that needs to know about Resend specifically — if we ever swap
# providers, this is the only file that changes.
#
# WHY FAILURES ARE LOGGED, NOT RAISED:
# Sending a verification email is a side effect of registration, not the
# core action. If Resend is down, registration should still succeed — the
# user account is real and usable, they just won't have a working
# verification link yet. This mirrors the same reasoning we already apply
# to audit logging: a side effect failing should not break the primary
# action. We log loudly so the failure is visible to us, without ever
# surfacing it to the client as a registration failure.

from typing import Optional

import resend

from core.config import settings
from monitoring.logger import get_logger

logger = get_logger(__name__)

resend.api_key = settings.RESEND_API_KEY


async def send_verification_email(to_email: str, verification_token: str) -> bool:
    """
    Sends an account verification email via Resend.

    Returns True if the send call succeeded, False otherwise.
    Never raises — see module docstring for why.
    """
    if not settings.RESEND_API_KEY:
        logger.warning(
            "verification_email_skipped",
            reason="RESEND_API_KEY not configured",
            no_phi_context=True,
            to_email=to_email,
        )
        return False

    verification_link = f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"

    try:
        resend.Emails.send({
            "from": settings.FROM_EMAIL,
            "to": to_email,
            "subject": "Verify your Pillara account",
            "html": _verification_email_html(verification_link),
        })
        logger.info("verification_email_sent", no_phi_context=True, to_email=to_email)
        return True

    except Exception as error:
        logger.error(
            "verification_email_failed",
            error=str(error),
            error_type=type(error).__name__,
            no_phi_context=True,
            to_email=to_email,
        )
        return False


async def send_password_reset_email(to_email: str, reset_token: str) -> bool:
    """
    Sends a password reset email via Resend.

    Returns True if the send call succeeded, False otherwise.
    Never raises — same reasoning as send_verification_email.

    SECURITY NOTE:
    The raw_token goes in the email link.
    The DB stores only the hash of the token.
    If this email is intercepted, the attacker gets the raw token —
    but it expires in PASSWORD_RESET_TOKEN_EXPIRE_MINUTES (default 30 min).
    """
    if not settings.RESEND_API_KEY:
        logger.warning(
            "password_reset_email_skipped",
            reason="RESEND_API_KEY not configured",
            no_phi_context=True,
            to_email=to_email,
        )
        return False

    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"

    try:
        resend.Emails.send({
            "from": settings.FROM_EMAIL,
            "to": to_email,
            "subject": "Reset your Pillara password",
            "html": _password_reset_email_html(reset_link),
        })
        logger.info("password_reset_email_sent", no_phi_context=True, to_email=to_email)
        return True

    except Exception as error:
        logger.error(
            "password_reset_email_failed",
            error=str(error),
            error_type=type(error).__name__,
            no_phi_context=True,
            to_email=to_email,
        )
        return False


def _password_reset_email_html(reset_link: str) -> str:
    return f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
        <h2>Reset your Pillara password</h2>
        <p>We received a request to reset your password. Click the button below to choose a new one:</p>
        <p>
            <a href="{reset_link}"
               style="display: inline-block; padding: 12px 24px; background: #2563eb;
                      color: #ffffff; text-decoration: none; border-radius: 6px;">
                Reset Password
            </a>
        </p>
        <p style="color: #666; font-size: 13px;">
            This link expires in 30 minutes.<br><br>
            If you didn't request a password reset, you can safely ignore this email.
            Your password will not change.<br><br>
            If the button doesn't work, copy and paste this link into your browser:<br>
            {reset_link}
        </p>
    </div>
    """


def _verification_email_html(verification_link: str) -> str:
    """
    Plain, functional HTML for the verification email.

    WHY PLAIN (not a polished branded template) FOR NOW:
    The goal right now is proving the mechanism works end to end — a real
    email arrives, the link works, the account gets verified. A polished
    branded template (logo, colors, proper React Email component) is a
    real but separate task, worth doing once alongside actual domain
    verification, not blocking this integration today.
    """
    return f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
        <h2>Verify your Pillara account</h2>
        <p>Thanks for signing up. Click the link below to verify your email address:</p>
        <p>
            <a href="{verification_link}"
               style="display: inline-block; padding: 12px 24px; background: #2563eb;
                      color: #ffffff; text-decoration: none; border-radius: 6px;">
                Verify Email
            </a>
        </p>
        <p style="color: #666; font-size: 13px;">
            If the button doesn't work, copy and paste this link into your browser:<br>
            {verification_link}
        </p>
    </div>
    """