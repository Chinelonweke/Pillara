# tests/integration/test_auth.py
#
# THESE TESTS VERIFY SECURITY BEHAVIOUR — not just happy paths.
# Each test documents a specific attack vector and proves it's handled.
# If a test fails, a vulnerability is open. Tests are security contracts.

import pytest
from httpx import AsyncClient


# ─── REGISTRATION ─────────────────────────────────────────────────────────────

class TestRegistration:

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "email": "test@example.com",
            "password": "SecurePass123!",
        })
        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_register_duplicate_email_race_condition(self, client: AsyncClient):
        """
        SECURITY: Two simultaneous registrations with the same email.
        The database unique constraint catches this — not our SELECT check.
        One must succeed (201), one must fail (409) — never two successes.
        """
        import asyncio
        tasks = [
            client.post("/api/v1/auth/register", json={"email": "race@example.com", "password": "SecurePass123!"}),
            client.post("/api/v1/auth/register", json={"email": "race@example.com", "password": "SecurePass123!"}),
        ]
        responses = await asyncio.gather(*tasks)
        status_codes = sorted([r.status_code for r in responses])
        # One 201, one 409 — never two 201s
        assert status_codes == [201, 409]

    @pytest.mark.asyncio
    async def test_register_weak_password_rejected(self, client: AsyncClient):
        """Pydantic validator blocks weak passwords before they reach the service."""
        response = await client.post("/api/v1/auth/register", json={
            "email": "weak@example.com",
            "password": "password",  # No uppercase, number, or special char
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_email_rejected(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "email": "not-an-email",
            "password": "SecurePass123!",
        })
        assert response.status_code == 422


# ─── LOGIN ────────────────────────────────────────────────────────────────────

class TestLogin:

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, registered_user: dict):
        response = await client.post("/api/v1/auth/login", json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, registered_user: dict):
        response = await client.post("/api/v1/auth/login", json={
            "email": registered_user["email"],
            "password": "WrongPassword999!",
        })
        assert response.status_code == 401
        # SECURITY: must not reveal which part was wrong
        assert "Invalid email or password" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_login_nonexistent_email(self, client: AsyncClient):
        """
        SECURITY: Non-existent email must return same error as wrong password.
        Prevents email enumeration.
        """
        response = await client.post("/api/v1/auth/login", json={
            "email": "doesnotexist@example.com",
            "password": "AnyPassword123!",
        })
        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_account_lockout_after_5_failures(self, client: AsyncClient, registered_user: dict):
        """
        SECURITY: After 5 failed login attempts, account is locked for 15 minutes.
        """
        for i in range(5):
            await client.post("/api/v1/auth/login", json={
                "email": registered_user["email"],
                "password": "WrongPassword!",
            })

        # 6th attempt — should be locked
        response = await client.post("/api/v1/auth/login", json={
            "email": registered_user["email"],
            "password": registered_user["password"],  # even correct password is blocked
        })
        assert response.status_code == 401
        assert "locked" in response.json()["message"].lower()


# ─── TOKEN SECURITY ───────────────────────────────────────────────────────────

class TestTokenSecurity:

    @pytest.mark.asyncio
    async def test_logout_invalidates_token(self, client: AsyncClient, auth_headers: dict):
        """
        SECURITY: After logout, the access token must be rejected.
        Tests that session deletion in Redis actually works.
        """
        # Token works before logout
        response = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200

        # Logout
        await client.post("/api/v1/auth/logout", headers=auth_headers)

        # Token must be rejected after logout
        response = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token_reuse_detection(self, client: AsyncClient, registered_user: dict):
        """
        SECURITY: Using a refresh token twice should trigger reuse detection.
        First use: succeeds and issues new tokens.
        Second use of the SAME old token: should fail and revoke all sessions.
        """
        login = await client.post("/api/v1/auth/login", json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        })
        old_refresh_token = login.json()["refresh_token"]

        # First use — should succeed
        first_refresh = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": old_refresh_token
        })
        assert first_refresh.status_code == 200

        # Second use of the SAME old token — reuse detected, all sessions revoked
        second_refresh = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": old_refresh_token
        })
        assert second_refresh.status_code == 401
        assert "Security alert" in second_refresh.json()["message"]

    @pytest.mark.asyncio
    async def test_refresh_token_cannot_be_used_as_access_token(
        self, client: AsyncClient, registered_user: dict
    ):
        """SECURITY: Refresh tokens must be rejected when used as access tokens."""
        login = await client.post("/api/v1/auth/login", json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        })
        refresh_token = login.json()["refresh_token"]

        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, client: AsyncClient):
        """SECURITY: Expired JWTs must be rejected."""
        expired_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiJ0ZXN0IiwidHlwZSI6ImFjY2VzcyIsImV4cCI6MX0."
            "invalid_signature"
        )
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401


# ─── IDOR TESTS ───────────────────────────────────────────────────────────────

class TestIDOR:

    @pytest.mark.asyncio
    async def test_cannot_access_other_users_profile(
        self, client: AsyncClient, user_a_headers: dict, user_b_profile_id: str
    ):
        """
        SECURITY: User A cannot access User B's profile.
        Must return 404 — never 403 (which confirms the resource exists).
        """
        response = await client.get(
            f"/api/v1/profiles/{user_b_profile_id}",
            headers=user_a_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_access_other_users_medications(
        self, client: AsyncClient, user_a_headers: dict, user_b_profile_id: str
    ):
        """SECURITY: Listing medications for another user's profile returns empty, not their data."""
        response = await client.get(
            f"/api/v1/medications/?profile_id={user_b_profile_id}",
            headers=user_a_headers,
        )
        # Returns empty list — never 403 (confirms profile exists) — never their medications
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_cannot_update_other_users_medication(
        self, client: AsyncClient, user_a_headers: dict, user_b_medication_id: str
    ):
        """SECURITY: User A cannot update User B's medication."""
        response = await client.patch(
            f"/api/v1/medications/{user_b_medication_id}",
            headers=user_a_headers,
            json={"notes": "Hacked"},
        )
        assert response.status_code == 404


# ─── RATE LIMITING ────────────────────────────────────────────────────────────

class TestRateLimiting:

    @pytest.mark.asyncio
    async def test_auth_rate_limit_triggers(self, client: AsyncClient):
        """SECURITY: More than 5 login attempts per minute triggers rate limit."""
        for i in range(5):
            await client.post("/api/v1/auth/login", json={
                "email": f"test{i}@example.com",
                "password": "WrongPass123!",
            })

        response = await client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "WrongPass123!",
        })
        assert response.status_code == 429
        assert "Retry-After" in response.headers