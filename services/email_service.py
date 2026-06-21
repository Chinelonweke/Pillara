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
        # Don't attempt to send with no key configured — log once, clearly,
        # rather than letting the Resend SDK fail with a less obvious error.
        logger.warning(
            "verification_email_skipped",
            reason="RESEND_API_KEY not configured",
            # WHY no_phi_context: to_email is genuinely needed here to debug
            # delivery issues, and this is a system configuration warning,
            # not a patient-data-bearing log line. See monitoring/logger.py
            # for the same reasoning applied to the FDA seeding script.
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
        # Broad except is deliberate here: Resend's SDK can raise several
        # different exception types (network errors, API errors, validation
        # errors), and we want ALL of them to result in the same outcome —
        # log it, return False, let registration continue.
        logger.error(
            "verification_email_failed",
            error=str(error),
            error_type=type(error).__name__,
            no_phi_context=True,
            to_email=to_email,
        )
        return False


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