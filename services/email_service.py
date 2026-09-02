# services/email_service.py

import resend

from core.config import settings
from monitoring.logger import get_logger

logger = get_logger(__name__)

resend.api_key = settings.RESEND_API_KEY


def _base_template(title: str, body: str, cta_text: str = None, cta_url: str = None, footer_note: str = None) -> str:
    cta_html = f"""
        <div style="text-align:center;margin:32px 0;">
            <a href="{cta_url}"
               style="display:inline-block;padding:14px 32px;background:#4A9B8E;
                      color:#ffffff;text-decoration:none;border-radius:8px;
                      font-weight:600;font-size:15px;letter-spacing:0.3px;">
                {cta_text}
            </a>
        </div>
    """ if cta_text and cta_url else ""

    footer_note_html = f"""
        <p style="color:#9ca3af;font-size:12px;margin-top:16px;line-height:1.6;">
            {footer_note}
        </p>
    """ if footer_note else ""

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
</head>
<body style="margin:0;padding:0;background-color:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f3f4f6;padding:40px 16px;">
        <tr>
            <td align="center">
                <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;">

                    <!-- Header -->
                    <tr>
                        <td style="background-color:#0F1B2D;border-radius:12px 12px 0 0;padding:24px 32px;">
                            <table cellpadding="0" cellspacing="0">
                                <tr>
                                    <td style="background-color:#4A9B8E;border-radius:8px;width:32px;height:32px;text-align:center;vertical-align:middle;">
                                        <span style="color:#ffffff;font-size:16px;font-weight:700;line-height:32px;display:block;">P</span>
                                    </td>
                                    <td style="padding-left:10px;">
                                        <span style="color:#ffffff;font-size:18px;font-weight:600;">Pillara</span>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Body -->
                    <tr>
                        <td style="background-color:#ffffff;padding:40px 32px;">
                            <h1 style="color:#0F1B2D;font-size:22px;font-weight:700;margin:0 0 16px 0;line-height:1.3;">
                                {title}
                            </h1>
                            <div style="color:#374151;font-size:15px;line-height:1.7;">
                                {body}
                            </div>
                            {cta_html}
                            {footer_note_html}
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background-color:#f9fafb;border-radius:0 0 12px 12px;border-top:1px solid #e5e7eb;padding:20px 32px;">
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td>
                                        <p style="color:#6b7280;font-size:12px;margin:0;line-height:1.6;">
                                            <strong style="color:#4A9B8E;">Pillara</strong> — Medication Safety Platform<br>
                                            <a href="https://pillara.site" style="color:#4A9B8E;text-decoration:none;">pillara.site</a>
                                        </p>
                                    </td>
                                    <td align="right">
                                        <p style="color:#9ca3af;font-size:11px;margin:0;">
                                            You received this email because<br>you have a Pillara account.
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>
    """


async def send_verification_email(to_email: str, verification_token: str) -> bool:
    if not settings.RESEND_API_KEY:
        logger.warning("verification_email_skipped", reason="RESEND_API_KEY not configured")
        return False

    verification_link = f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"

    body = """
        <p>Thanks for signing up. Please verify your email address to activate your account
        and access all medication safety features.</p>
        <p>This link expires in <strong>24 hours</strong>.</p>
    """

    try:
        resend.Emails.send({
            "from": settings.FROM_EMAIL,
            "to": to_email,
            "subject": "Verify your Pillara account",
            "html": _base_template(
                title="Verify your email address",
                body=body,
                cta_text="Verify Email",
                cta_url=verification_link,
                footer_note=f"If the button doesn't work, copy this link into your browser: {verification_link}",
            ),
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

    body = """
        <p>We received a request to reset your password. Click the button below to choose a new one.</p>
        <p>This link expires in <strong>30 minutes</strong>. If you didn't request a password reset,
        you can safely ignore this email — your password will not change.</p>
    """

    try:
        resend.Emails.send({
            "from": settings.FROM_EMAIL,
            "to": to_email,
            "subject": "Reset your Pillara password",
            "html": _base_template(
                title="Reset your password",
                body=body,
                cta_text="Reset Password",
                cta_url=reset_link,
                footer_note=f"If the button doesn't work, copy this link into your browser: {reset_link}",
            ),
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

    body = f"""
        <p><strong>{inviter_name}</strong> has invited you to access a medication profile on Pillara.</p>
        <p>Your role: <strong style="color:#4A9B8E;text-transform:capitalize;">{role}</strong>
        — you will be able to {role_description}.</p>
        <p>Pillara is a medication safety platform that helps caregivers and families manage
        medications safely and check for dangerous interactions.</p>
        <p>This invitation expires in <strong>7 days</strong>.</p>
    """

    try:
        resend.Emails.send({
            "from": settings.FROM_EMAIL,
            "to": to_email,
            "subject": f"{inviter_name} invited you to Pillara",
            "html": _base_template(
                title="You have a Pillara invitation",
                body=body,
                cta_text="Accept Invitation",
                cta_url=invite_link,
                footer_note=f"If you don't know {inviter_name} or didn't expect this, ignore this email. If the button doesn't work: {invite_link}",
            ),
        })
        logger.info("profile_invite_email_sent", role=role)
        return True
    except Exception as error:
        logger.error("profile_invite_email_failed", error=str(error))
        return False


async def send_profile_claim_email(to_email: str, claim_link: str, caregiver_email: str) -> bool:
    if not settings.RESEND_API_KEY:
        return False

    body = f"""
        <p><strong>{caregiver_email}</strong> has created a medication profile for you on Pillara,
        a medication safety platform.</p>
        <p>You can:</p>
        <ul style="color:#374151;padding-left:20px;margin:12px 0;">
            <li style="margin-bottom:8px;"><strong>Claim this profile</strong> — sign up and become the owner.
            You'll have full control over your medication data.</li>
            <li><strong>Ignore this email</strong> — your caregiver will continue managing your medications.</li>
        </ul>
        <p>This link expires in <strong>7 days</strong>.</p>
    """

    try:
        resend.Emails.send({
            "from": settings.FROM_EMAIL,
            "to": to_email,
            "subject": "A medication profile was created for you on Pillara",
            "html": _base_template(
                title="Your caregiver created a profile for you",
                body=body,
                cta_text="Claim My Profile",
                cta_url=claim_link,
                footer_note=f"If you don't know {caregiver_email}, ignore this email. If the button doesn't work: {claim_link}",
            ),
        })
        logger.info("profile_claim_email_sent")
        return True
    except Exception as error:
        logger.error("profile_claim_email_failed", error=str(error))
        return False


async def send_reminder_email(to_email: str, medication_name: str, dosage: str, profile_name: str) -> bool:
    if not settings.RESEND_API_KEY:
        return False

    body = f"""
        <p>This is a reminder to take your medication.</p>
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px;margin:20px 0;">
            <p style="margin:0;font-size:18px;font-weight:600;color:#0F1B2D;">
                💊 {medication_name}
            </p>
            {f'<p style="margin:8px 0 0 0;color:#6b7280;">{dosage}</p>' if dosage else ''}
            {f'<p style="margin:8px 0 0 0;color:#6b7280;font-size:13px;">Profile: {profile_name}</p>' if profile_name else ''}
        </div>
        <p>Please take your medication as prescribed. If you have any concerns,
        contact your doctor or pharmacist.</p>
    """

    try:
        resend.Emails.send({
            "from": settings.FROM_EMAIL,
            "to": to_email,
            "subject": f"Medication reminder: {medication_name}",
            "html": _base_template(
                title="Time to take your medication",
                body=body,
                footer_note="You are receiving this because you set up a medication reminder on Pillara.",
            ),
        })
        logger.info("reminder_email_sent", medication=medication_name)
        return True
    except Exception as error:
        logger.error("reminder_email_failed", error=str(error))
        return False