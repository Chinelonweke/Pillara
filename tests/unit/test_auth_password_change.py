# tests/unit/test_auth_password_change.py
#
# Regression tests for the change-password endpoint:
# 1. Must null the refresh token so a stolen refresh token can't outlive a
#    password change (the same protection reset_password already had).
# 2. Must enforce the same password-strength rules as signup, not just length.
# No database/Redis required — dependencies are mocked.

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.routers.auth import change_password
from core.exceptions import ValidationError
from core.security import hash_password


def _make_user(password: str = "OldPassword123!"):
    return SimpleNamespace(
        id="user-1",
        hashed_password=hash_password(password),
        refresh_token_jti="some-jti",
        refresh_token_expires="2099-01-01",
    )


@pytest.mark.asyncio
async def test_change_password_nulls_refresh_token():
    user = _make_user()
    mock_db = MagicMock()
    mock_db.commit = AsyncMock()

    with patch("core.redis_client.SessionManager") as MockSessionManager:
        MockSessionManager.return_value.revoke_all_sessions = AsyncMock(return_value=1)

        await change_password(
            body={"current_password": "OldPassword123!", "new_password": "NewPassword456!"},
            current_user=user,
            db=mock_db,
            redis=MagicMock(),
        )

    assert user.refresh_token_jti is None
    assert user.refresh_token_expires is None


@pytest.mark.asyncio
async def test_change_password_rejects_weak_new_password():
    """New password must pass the same complexity rules as signup, not just length>=8."""
    user = _make_user()
    mock_db = MagicMock()
    mock_db.commit = AsyncMock()

    with pytest.raises(ValidationError):
        await change_password(
            body={"current_password": "OldPassword123!", "new_password": "alllowercase1"},
            current_user=user,
            db=mock_db,
            redis=MagicMock(),
        )
