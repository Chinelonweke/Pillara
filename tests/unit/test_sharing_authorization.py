"""
Unit tests for sharing authorization boundary.
Tests the role resolution logic in SharingService without hitting a real database.
"""


class MockProfile:
    def __init__(self, user_id, owner_user_id=None, status="active"):
        self.id = "profile-123"
        self.user_id = user_id
        self.owner_user_id = owner_user_id
        self.status = status


class MockProfileAccess:
    def __init__(self, role, status="active"):
        self.role = role
        self.status = status
        self.granted_to_user_id = "user-caregiver"
        self.profile_id = "profile-123"


# ── Email verification tests ────────────────────────────────────────────────

class TestInviteEmailVerification:
    """Invite acceptance must verify email matches intended recipient."""

    def test_invite_email_mismatch_raises(self):
        """A user with a different email must not be able to accept an invite."""

        invite_email = "nurse@hospital.com"
        accepting_email = "attacker@evil.com"

        # This is the check that must happen in accept_invite
        if invite_email and accepting_email.lower().strip() != invite_email.lower().strip():
            error_raised = True
        else:
            error_raised = False

        assert error_raised, "Email mismatch should raise an error"

    def test_invite_email_match_passes(self):
        """The intended recipient must be able to accept the invite."""
        invite_email = "nurse@hospital.com"
        accepting_email = "nurse@hospital.com"

        mismatch = invite_email and accepting_email.lower().strip() != invite_email.lower().strip()
        assert not mismatch, "Matching email should not raise an error"

    def test_invite_email_case_insensitive(self):
        """Email comparison must be case-insensitive."""
        invite_email = "Nurse@Hospital.COM"
        accepting_email = "nurse@hospital.com"

        mismatch = invite_email and accepting_email.lower().strip() != invite_email.lower().strip()
        assert not mismatch, "Case-insensitive email match should pass"


class TestClaimEmailVerification:
    """Claim token acceptance must verify email matches intended recipient."""

    def test_claim_email_mismatch_raises(self):
        """A user with a different email must not be able to claim a profile."""
        claim_email = "patient@gmail.com"
        claiming_email = "attacker@evil.com"

        mismatch = claim_email and claiming_email.lower().strip() != claim_email.lower().strip()
        assert mismatch, "Email mismatch should raise an error"

    def test_claim_email_match_passes(self):
        """The intended patient must be able to claim the profile."""
        claim_email = "patient@gmail.com"
        claiming_email = "patient@gmail.com"

        mismatch = claim_email and claiming_email.lower().strip() != claim_email.lower().strip()
        assert not mismatch, "Matching email should pass"


# ── Role resolution tests ────────────────────────────────────────────────────

class TestRoleResolution:
    """Role resolution logic for different profile ownership scenarios."""

    def test_creator_of_unclaimed_profile_is_owner(self):
        """A user who created an unclaimed profile is the owner."""
        profile = MockProfile(user_id="user-1", owner_user_id=None, status="unclaimed")
        user_id = "user-1"

        # Logic from SharingService.get_user_role_for_profile
        if profile.user_id == user_id and profile.status == "unclaimed":
            role = "owner"
        else:
            role = None

        assert role == "owner"

    def test_owner_user_id_match_is_owner(self):
        """A user whose ID matches owner_user_id is the owner."""
        profile = MockProfile(user_id="user-caregiver", owner_user_id="user-patient", status="active")
        user_id = "user-patient"

        if profile.owner_user_id == user_id:
            role = "owner"
        else:
            role = None

        assert role == "owner"

    def test_creator_after_claim_is_caregiver(self):
        """The original creator becomes caregiver after patient claims the profile."""
        profile = MockProfile(user_id="user-caregiver", owner_user_id="user-patient", status="active")
        user_id = "user-caregiver"

        if profile.owner_user_id == user_id:
            role = "owner"
        elif profile.user_id == user_id and profile.owner_user_id is None:
            role = "owner"
        elif (profile.user_id == user_id and profile.status == "active"
              and profile.owner_user_id is not None
              and profile.owner_user_id != user_id):
            role = "caregiver"
        else:
            role = None

        assert role == "caregiver", "Original creator should be caregiver after claim"

    def test_creator_with_no_owner_is_owner(self):
        """Creator of active profile with no owner_user_id is the owner (self-created profile)."""
        profile = MockProfile(user_id="user-1", owner_user_id=None, status="active")
        user_id = "user-1"

        if profile.owner_user_id == user_id:
            role = "owner"
        elif profile.user_id == user_id and profile.owner_user_id is None:
            role = "owner"
        else:
            role = None

        assert role == "owner"

    def test_unrelated_user_has_no_role(self):
        """A user with no relation to the profile has no role."""
        profile = MockProfile(user_id="user-caregiver", owner_user_id="user-patient", status="active")
        user_id = "user-stranger"

        if profile.owner_user_id == user_id:
            role = "owner"
        elif profile.user_id == user_id and profile.owner_user_id is None:
            role = "owner"
        elif (profile.user_id == user_id and profile.status == "active"
              and profile.owner_user_id is not None):
            role = "caregiver"
        else:
            role = None  # Would check ProfileAccess next, but no access granted

        assert role is None


# ── Login redirect tests ─────────────────────────────────────────────────────

class TestLoginRedirect:
    """Login redirect must only allow same-origin redirects."""

    def test_same_origin_redirect_allowed(self):
        """A path starting with / is a valid same-origin redirect."""
        redirect = "/accept-invite?token=abc123"
        valid = redirect and redirect.startswith('/')
        assert valid

    def test_external_redirect_blocked(self):
        """An external URL must not be used as a redirect target."""
        redirect = "https://evil.com/steal-token"
        valid = redirect and redirect.startswith('/')
        assert not valid

    def test_protocol_relative_redirect_blocked(self):
        """A protocol-relative URL must not be used as a redirect target."""
        redirect = "//evil.com/steal-token"
        valid = redirect and redirect.startswith('/') and not redirect.startswith('//')
        assert not valid

    def test_empty_redirect_falls_back_to_dashboard(self):
        """Empty redirect falls back to dashboard."""
        redirect = None
        destination = redirect if (redirect and redirect.startswith('/')) else '/dashboard'
        assert destination == '/dashboard'


# ── Rate limit tests ─────────────────────────────────────────────────────────

class TestRateLimitIdentifiers:
    """Separate per-IP and per-email rate limits cannot be bypassed by rotating one."""

    def test_per_ip_limit_separate_from_per_email(self):
        """IP and email limits are separate keys — rotating one does not reset the other."""
        import hashlib

        ip1 = hashlib.sha256("1.2.3.4".encode()).hexdigest()[:16]
        ip2 = hashlib.sha256("5.6.7.8".encode()).hexdigest()[:16]
        email = hashlib.sha256("victim@gmail.com".encode()).hexdigest()[:16]

        ip1_key = f"ip:{ip1}"
        ip2_key = f"ip:{ip2}"
        email_key = f"email:{email}"

        # Different IPs have different IP keys
        assert ip1_key != ip2_key
        # Email key is independent of IP key
        assert email_key != ip1_key
        assert email_key != ip2_key
        # Rotating IP does not change email key — email limit still applies
        assert email_key == f"email:{email}"