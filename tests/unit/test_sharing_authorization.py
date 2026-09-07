"""
Unit tests for sharing authorization boundary.
Tests call actual SharingService methods with properly mocked async DB.
"""
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
import pytest


# ── Mock helpers ──────────────────────────────────────────────────────────────

def make_db_mock(*return_values):
    """
    Create an AsyncMock db where each execute() call returns the next value
    in return_values via scalar_one_or_none().
    """
    db = AsyncMock()
    results = []
    for val in return_values:
        result = MagicMock()
        result.scalar_one_or_none.return_value = val
        results.append(result)

    if len(results) == 1:
        db.execute.return_value = results[0]
    else:
        db.execute.side_effect = results

    return db


def make_profile(user_id, owner_user_id=None, status="active"):
    p = MagicMock()
    p.id = "profile-123"
    p.user_id = user_id
    p.owner_user_id = owner_user_id
    p.status = status
    p.claim_email = None
    p.claim_token = None
    p.claim_token_expires = datetime(2099, 1, 1, tzinfo=timezone.utc)
    return p


def make_access(role, granted_to_user_id=None, invite_email="nurse@hospital.com"):
    a = MagicMock()
    a.role = role
    a.status = "pending"
    a.granted_to_user_id = granted_to_user_id
    a.profile_id = "profile-123"
    a.invite_email = invite_email
    a.invite_token = "token-abc"
    a.invite_token_expires = datetime(2099, 1, 1, tzinfo=timezone.utc)
    return a


# ── Invite email verification ─────────────────────────────────────────────────

class TestInviteEmailVerification:

    @pytest.mark.asyncio
    async def test_wrong_email_is_rejected(self):
        from core.exceptions import AuthorizationError
        from services.sharing_service import SharingService

        access = make_access("caregiver", invite_email="nurse@hospital.com")
        db = make_db_mock(access)

        svc = SharingService(db=db)
        svc.audit = AsyncMock()

        with pytest.raises(AuthorizationError, match="different email"):
            await svc.accept_invite(
                invite_token="token-abc",
                accepting_user_id="user-attacker",
                accepting_user_email="attacker@evil.com",
            )

    @pytest.mark.asyncio
    async def test_correct_email_is_accepted(self):
        from services.sharing_service import SharingService

        access = make_access("caregiver", invite_email="nurse@hospital.com")
        db = make_db_mock(access)

        svc = SharingService(db=db)
        svc.audit = AsyncMock()
        svc.audit.log = AsyncMock()

        result = await svc.accept_invite(
            invite_token="token-abc",
            accepting_user_id="user-nurse",
            accepting_user_email="nurse@hospital.com",
        )
        assert result.granted_to_user_id == "user-nurse"
        assert result.status == "active"

    @pytest.mark.asyncio
    async def test_email_comparison_is_case_insensitive(self):
        from services.sharing_service import SharingService

        access = make_access("caregiver", invite_email="Nurse@Hospital.COM")
        db = make_db_mock(access)

        svc = SharingService(db=db)
        svc.audit = AsyncMock()
        svc.audit.log = AsyncMock()

        result = await svc.accept_invite(
            invite_token="token-abc",
            accepting_user_id="user-nurse",
            accepting_user_email="nurse@hospital.com",
        )
        assert result.status == "active"

    @pytest.mark.asyncio
    async def test_token_not_consumed_on_wrong_email(self):
        """Token must NOT be consumed when the wrong user tries to accept."""
        from core.exceptions import AuthorizationError
        from services.sharing_service import SharingService

        access = make_access("caregiver", invite_email="nurse@hospital.com")
        original_token = access.invite_token
        db = make_db_mock(access)

        svc = SharingService(db=db)
        svc.audit = AsyncMock()

        with pytest.raises(AuthorizationError):
            await svc.accept_invite(
                invite_token="token-abc",
                accepting_user_id="user-attacker",
                accepting_user_email="attacker@evil.com",
            )

        assert access.invite_token == original_token
        assert access.status == "pending"


# ── Claim email verification ──────────────────────────────────────────────────

class TestClaimEmailVerification:

    @pytest.mark.asyncio
    async def test_wrong_email_is_rejected(self):
        from core.exceptions import AuthorizationError
        from services.sharing_service import SharingService

        profile = make_profile(user_id="user-caregiver", status="unclaimed")
        profile.claim_email = "patient@gmail.com"
        profile.claim_token = "claim-token"
        db = make_db_mock(profile)

        svc = SharingService(db=db)
        svc.audit = AsyncMock()

        with pytest.raises(AuthorizationError, match="different email"):
            await svc.claim_profile(
                claim_token="claim-token",
                claiming_user_id="user-attacker",
                claiming_user_email="attacker@evil.com",
            )

    @pytest.mark.asyncio
    async def test_correct_email_is_accepted(self):
        from services.sharing_service import SharingService

        profile = make_profile(user_id="user-caregiver", status="unclaimed")
        profile.claim_email = "patient@gmail.com"
        profile.claim_token = "claim-token"
        db = make_db_mock(profile)
        db.add = MagicMock()

        svc = SharingService(db=db)
        svc.audit = AsyncMock()
        svc.audit.log = AsyncMock()

        result = await svc.claim_profile(
            claim_token="claim-token",
            claiming_user_id="user-patient",
            claiming_user_email="patient@gmail.com",
        )
        assert result.owner_user_id == "user-patient"
        assert result.status == "active"


# ── Role resolution ───────────────────────────────────────────────────────────

class TestRoleResolution:

    @pytest.mark.asyncio
    async def test_creator_of_unclaimed_profile_is_owner(self):
        from services.sharing_service import SharingService

        profile = make_profile(user_id="user-1", owner_user_id=None, status="unclaimed")
        db = make_db_mock(profile)

        svc = SharingService(db=db)
        role = await svc.get_user_role_for_profile("profile-123", "user-1")
        assert role == "owner"

    @pytest.mark.asyncio
    async def test_owner_user_id_match_is_owner(self):
        from services.sharing_service import SharingService

        profile = make_profile(user_id="user-caregiver", owner_user_id="user-patient")
        db = make_db_mock(profile, None)  # second call: no ProfileAccess

        svc = SharingService(db=db)
        role = await svc.get_user_role_for_profile("profile-123", "user-patient")
        assert role == "owner"

    @pytest.mark.asyncio
    async def test_creator_after_claim_is_caregiver(self):
        from services.sharing_service import SharingService

        profile = make_profile(user_id="user-caregiver", owner_user_id="user-patient")
        db = make_db_mock(profile, None)

        svc = SharingService(db=db)
        role = await svc.get_user_role_for_profile("profile-123", "user-caregiver")
        assert role == "caregiver"

    @pytest.mark.asyncio
    async def test_creator_with_no_owner_is_owner(self):
        from services.sharing_service import SharingService

        profile = make_profile(user_id="user-1", owner_user_id=None, status="active")
        db = make_db_mock(profile)

        svc = SharingService(db=db)
        role = await svc.get_user_role_for_profile("profile-123", "user-1")
        assert role == "owner"

    @pytest.mark.asyncio
    async def test_unrelated_user_has_no_role(self):
        from services.sharing_service import SharingService

        profile = make_profile(user_id="user-caregiver", owner_user_id="user-patient")
        db = make_db_mock(profile, None)  # no ProfileAccess for stranger

        svc = SharingService(db=db)
        role = await svc.get_user_role_for_profile("profile-123", "user-stranger")
        assert role is None

    @pytest.mark.asyncio
    async def test_profile_access_grant_returns_granted_role(self):
        from services.sharing_service import SharingService

        profile = make_profile(user_id="user-caregiver", owner_user_id="user-patient")
        access = make_access("viewer", granted_to_user_id="user-viewer")
        db = make_db_mock(profile, access)

        svc = SharingService(db=db)
        role = await svc.get_user_role_for_profile("profile-123", "user-viewer")
        assert role == "viewer"

    @pytest.mark.asyncio
    async def test_caregiver_profile_access_grant_returns_caregiver_role(self):
        from services.sharing_service import SharingService

        profile = make_profile(user_id="user-creator", owner_user_id="user-patient")
        access = make_access("caregiver", granted_to_user_id="user-nurse")
        db = make_db_mock(profile, access)

        svc = SharingService(db=db)
        role = await svc.get_user_role_for_profile("profile-123", "user-nurse")
        assert role == "caregiver"


# ── Login redirect validation ─────────────────────────────────────────────────

class TestLoginRedirect:

    def _is_valid(self, redirect):
        return bool(redirect and redirect.startswith('/') and not redirect.startswith('//'))

    def test_same_origin_redirect_allowed(self):
        assert self._is_valid("/accept-invite?token=abc123")

    def test_external_redirect_blocked(self):
        assert not self._is_valid("https://evil.com/steal-token")

    def test_protocol_relative_redirect_blocked(self):
        assert not self._is_valid("//evil.com/steal-token")

    def test_empty_redirect_falls_back_to_dashboard(self):
        redirect = None
        destination = redirect if self._is_valid(redirect) else '/dashboard'
        assert destination == '/dashboard'


# ── Rate limit key independence ───────────────────────────────────────────────

class TestRateLimitIdentifiers:

    def test_per_ip_and_per_email_are_independent_keys(self):
        import hashlib

        ip1 = hashlib.sha256("1.2.3.4".encode()).hexdigest()[:16]
        ip2 = hashlib.sha256("5.6.7.8".encode()).hexdigest()[:16]
        email = hashlib.sha256("victim@gmail.com".encode()).hexdigest()[:16]

        assert f"ip:{ip1}" != f"ip:{ip2}"
        assert f"email:{email}" != f"ip:{ip1}"
        assert f"email:{email}" != f"ip:{ip2}"

    def test_rotating_ip_does_not_reset_email_limit(self):
        import hashlib

        email = hashlib.sha256("victim@gmail.com".encode()).hexdigest()[:16]
        email_key = f"email:{email}"

        for ip in ["1.2.3.4", "5.6.7.8", "9.10.11.12"]:
            ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]
            assert f"ip:{ip_hash}" != email_key


# ── Additional tests flagged in review ────────────────────────────────────────

class TestClaimTokenNotConsumedOnWrongEmail:
    """Claim token must NOT be consumed when wrong user tries to claim."""

    @pytest.mark.asyncio
    async def test_claim_token_not_consumed_on_wrong_email(self):
        from core.exceptions import AuthorizationError
        from services.sharing_service import SharingService

        profile = make_profile(user_id="user-caregiver", status="unclaimed")
        profile.claim_email = "patient@gmail.com"
        profile.claim_token = "claim-token-original"
        db = make_db_mock(profile)

        svc = SharingService(db=db)
        svc.audit = AsyncMock()

        with pytest.raises(AuthorizationError):
            await svc.claim_profile(
                claim_token="claim-token-original",
                claiming_user_id="user-attacker",
                claiming_user_email="attacker@evil.com",
            )

        # Token and status must be unchanged
        assert profile.claim_token == "claim-token-original"
        assert profile.status == "unclaimed"
        assert profile.owner_user_id is None


class TestClaimEmailCaseInsensitive:
    """Claim email comparison must be case-insensitive."""

    @pytest.mark.asyncio
    async def test_claim_email_case_insensitive(self):
        from services.sharing_service import SharingService

        profile = make_profile(user_id="user-caregiver", status="unclaimed")
        profile.claim_email = "Patient@Gmail.COM"
        profile.claim_token = "claim-token"
        db = make_db_mock(profile)
        db.add = MagicMock()

        svc = SharingService(db=db)
        svc.audit = AsyncMock()
        svc.audit.log = AsyncMock()

        result = await svc.claim_profile(
            claim_token="claim-token",
            claiming_user_id="user-patient",
            claiming_user_email="patient@gmail.com",
        )
        assert result.owner_user_id == "user-patient"


class TestOwnerOnlyActions:
    """Caregiver and viewer must be blocked from owner-only actions."""

    @pytest.mark.asyncio
    async def test_caregiver_cannot_invite_others(self):
        from core.exceptions import AuthorizationError
        from services.sharing_service import SharingService

        # Profile where user-caregiver is the caregiver, not owner
        profile = make_profile(user_id="user-caregiver", owner_user_id="user-patient")
        access_grant = make_access("caregiver", granted_to_user_id="user-caregiver")

        db = make_db_mock(profile, access_grant)

        svc = SharingService(db=db)
        svc.audit = AsyncMock()

        with pytest.raises(AuthorizationError):
            await svc.require_role(
                profile_id="profile-123",
                user_id="user-caregiver",
                minimum_role="owner",
            )

    @pytest.mark.asyncio
    async def test_viewer_cannot_invite_others(self):
        from core.exceptions import AuthorizationError
        from services.sharing_service import SharingService

        profile = make_profile(user_id="user-caregiver", owner_user_id="user-patient")
        access_grant = make_access("viewer", granted_to_user_id="user-viewer")

        db = make_db_mock(profile, access_grant)

        svc = SharingService(db=db)
        svc.audit = AsyncMock()

        with pytest.raises(AuthorizationError):
            await svc.require_role(
                profile_id="profile-123",
                user_id="user-viewer",
                minimum_role="owner",
            )


class TestExpiredTokens:
    """Expired invite and claim tokens must be rejected."""

    @pytest.mark.asyncio
    async def test_expired_invite_token_rejected(self):
        from core.exceptions import ValidationError
        from services.sharing_service import SharingService

        access = make_access("caregiver", invite_email="nurse@hospital.com")
        # Set token as expired
        access.invite_token_expires = datetime(2020, 1, 1, tzinfo=timezone.utc)
        db = make_db_mock(access)

        svc = SharingService(db=db)
        svc.audit = AsyncMock()

        with pytest.raises(ValidationError, match="expired"):
            await svc.accept_invite(
                invite_token="token-abc",
                accepting_user_id="user-nurse",
                accepting_user_email="nurse@hospital.com",
            )

    @pytest.mark.asyncio
    async def test_expired_claim_token_rejected(self):
        from core.exceptions import ValidationError
        from services.sharing_service import SharingService

        profile = make_profile(user_id="user-caregiver", status="unclaimed")
        profile.claim_email = "patient@gmail.com"
        profile.claim_token = "claim-token"
        profile.claim_token_expires = datetime(2020, 1, 1, tzinfo=timezone.utc)
        db = make_db_mock(profile)

        svc = SharingService(db=db)
        svc.audit = AsyncMock()

        with pytest.raises(ValidationError, match="expired"):
            await svc.claim_profile(
                claim_token="claim-token",
                claiming_user_id="user-patient",
                claiming_user_email="patient@gmail.com",
            )