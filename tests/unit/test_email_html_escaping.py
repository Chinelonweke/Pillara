# tests/unit/test_email_html_escaping.py
#
# Regression test: send_profile_invite_email and send_profile_claim_email must
# HTML-escape user-supplied values before interpolating into email HTML, the
# same defence already applied to send_reminder_email. Without it, a caregiver
# name or invite email could inject arbitrary HTML into emails sent from
# Pillara's real domain.

from unittest.mock import patch

import pytest

from services.email_service import send_profile_invite_email, send_profile_claim_email


@pytest.mark.asyncio
async def test_invite_email_escapes_inviter_name():
    malicious_name = "<script>alert(1)</script>"
    with patch("services.email_service.settings") as mock_settings, \
         patch("services.email_service.resend") as mock_resend:
        mock_settings.RESEND_API_KEY = "test-key"
        mock_settings.FROM_EMAIL = "noreply@pillara.test"
        captured = {}
        mock_resend.Emails.send = lambda payload: captured.update(payload)

        await send_profile_invite_email(
            to_email="patient@example.com",
            invite_link="https://pillara.test/invite/abc",
            role="caregiver",
            inviter_name=malicious_name,
        )

    assert "<script>" not in captured["html"]
    assert "&lt;script&gt;" in captured["html"]


@pytest.mark.asyncio
async def test_claim_email_escapes_caregiver_email():
    malicious_email = '"><img src=x onerror=alert(1)>'
    with patch("services.email_service.settings") as mock_settings, \
         patch("services.email_service.resend") as mock_resend:
        mock_settings.RESEND_API_KEY = "test-key"
        mock_settings.FROM_EMAIL = "noreply@pillara.test"
        captured = {}
        mock_resend.Emails.send = lambda payload: captured.update(payload)

        await send_profile_claim_email(
            to_email="patient@example.com",
            claim_link="https://pillara.test/claim/abc",
            caregiver_email=malicious_email,
        )

    assert "<img src=x" not in captured["html"]
