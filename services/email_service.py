# services/email_service.py
from typing import Optional

import resend

from core.config import settings
from monitoring.logger import get_logger

logger = get_logger(__name__)

resend.api_key = settings.RESEND_API_KEY


async def send_verification_email(to_email: str, verification_token: str) -> bool:
    if not settings.RESEND_API_KEY:
        logger.warning("verification_email_skipped", reason="RESEND_API_KEY not configured")
        return False

    verification_link = f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"

    try:
        resend.Emails.send({
            "from": settings.FROM_EMAIL,
            "to": to_email,
            "subject": "Verify your Pillara account",
            "html": _verification_email_html(verification_link),
        })
        logger.info("verification_email_sent")
        return True
    except Exception as error:
        logger.error("verification_email_failed", error=str(error), error_type=type(error).__name__)
        return False


async def send_password_reset_email(to_email: str, reset_token: str) -> bool:
    if not settings.RESEND_API_KEY:
        logger.warning("password_reset_email_skipped", reason="RESEND_API_KEY not configured")
        return False

    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"

    try:
        resend.Emails.send({
            "from": settings.FROM_EMAIL,
            "to": to_email,
            "subject": "Reset your Pillara password",
            "html": _password_reset_email_html(reset_link),
        })
        logger.info("password_reset_email_sent")
        return True
    except Exception as error:
        logger.error("password_reset_email_failed", error=str(error), error_type=type(error).__name__)
        return False


async def send_profile_invite_email(to_email: str, invite_link: str, role: str, inviter_name: str) -> bool:
    if not settings.RESEND_API_KEY:
        return False

    role_description = {
        "caregiver": "view medications and add new ones",
        "viewer": "view medications (read only)",
    }.get(role, "access the profile")

    try:
        resend.Emails.send({
            "from": settings.FROM_EMAIL,
            "to": to_email,
            "subject": "You've been invited to access a Pillara profile",
            "html": f"""
            <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
                <h2>You have a Pillara invitation</h2>
                <p><strong>{inviter_name}</strong> has invited you to {role_description}.</p>
                <p><a href="{invite_link}" style="display:inline-block;padding:12px 24px;background:#4A9B8E;color:#fff;text-decoration:none;border-radius:6px;">Accept Invitation</a></p>
                <p style="color:#666;font-size:13px;">This link expires in 7 days. If you don't know {inviter_name}, ignore this email.</p>
            </div>
            """,
        })
        logger.info("profile_invite_email_sent", role=role)
        return True
    except Exception as error:
        logger.error("profile_invite_email_failed", error=str(error))
        return False


async def send_profile_claim_email(to_email: str, claim_link: str, caregiver_email: str) -> bool:
    if not settings.RESEND_API_KEY:
        return False

    try:
        resend.Emails.send({
            "from": settings.FROM_EMAIL,
            "to": to_email,
            "subject": "A medication profile has been created for you on Pillara",
            "html": f"""
            <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
                <h2>A profile was created for you</h2>
                <p><strong>{caregiver_email}</strong> has created a medication profile for you on Pillara.</p>
                <p>You can claim ownership of it, or ignore this email and let your caregiver manage it.</p>
                <p><a href="{claim_link}" style="display:inline-block;padding:12px 24px;background:#4A9B8E;color:#fff;text-decoration:none;border-radius:6px;">Claim My Profile</a></p>
                <p style="color:#666;font-size:13px;">This link expires in 7 days. If you don't know {caregiver_email}, ignore this email.</p>
            </div>
            """,
        })
        logger.info("profile_claim_email_sent")
        return True
    except Exception as error:
        logger.error("profile_claim_email_failed", error=str(error))
        return False


def _verification_email_html(verification_link: str) -> str:
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
            If you didn't request a password reset, you can safely ignore this email.<br><br>
            If the button doesn't work, copy and paste this link into your browser:<br>
            {reset_link}
        </p>
    </div>
    """