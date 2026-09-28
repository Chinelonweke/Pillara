"""Tests for the deployment safeguards added in fix/deployed-env-safeguards."""
from types import SimpleNamespace

import pytest

from core import security
from core.secrets_loader import load_secrets_from_infisical


def fake_request(direct_ip, forwarded_for=None):
    headers = {"X-Forwarded-For": forwarded_for} if forwarded_for else {}
    return SimpleNamespace(client=SimpleNamespace(host=direct_ip), headers=headers)


# ── get_client_ip ────────────────────────────────────────────────────────────

@pytest.fixture
def trusted_localhost(monkeypatch):
    monkeypatch.setattr(security.settings, "TRUSTED_PROXY_IPS", "127.0.0.1")


def test_spoofed_header_from_untrusted_source_is_ignored(trusted_localhost):
    req = fake_request("203.0.113.9", forwarded_for="1.2.3.4")
    assert security.get_client_ip(req) == "203.0.113.9"


def test_trusted_proxy_uses_last_entry_not_forged_first(trusted_localhost):
    req = fake_request("127.0.0.1", forwarded_for="1.2.3.4, 198.51.100.7")
    assert security.get_client_ip(req) == "198.51.100.7"


def test_trusted_proxy_without_header_uses_direct_ip(trusted_localhost):
    req = fake_request("127.0.0.1")
    assert security.get_client_ip(req) == "127.0.0.1"


# ── deployment_safety_check ──────────────────────────────────────────────────

STRONG_KEY = "a" * 64


@pytest.mark.parametrize("env", ["staging", "production"])
def test_debug_true_blocks_startup_when_deployed(monkeypatch, env):
    monkeypatch.setattr(security.settings, "ENVIRONMENT", env)
    monkeypatch.setattr(security.settings, "DEBUG", True)
    monkeypatch.setattr(security.settings, "JWT_SECRET_KEY", STRONG_KEY)
    with pytest.raises(RuntimeError, match="DEBUG=True"):
        security.deployment_safety_check()


@pytest.mark.parametrize("env", ["staging", "production"])
def test_short_jwt_key_blocks_startup_when_deployed(monkeypatch, env):
    monkeypatch.setattr(security.settings, "ENVIRONMENT", env)
    monkeypatch.setattr(security.settings, "DEBUG", False)
    monkeypatch.setattr(security.settings, "JWT_SECRET_KEY", "a" * 32)
    with pytest.raises(RuntimeError, match="too short"):
        security.deployment_safety_check()


def test_development_is_not_blocked(monkeypatch):
    monkeypatch.setattr(security.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(security.settings, "DEBUG", True)
    monkeypatch.setattr(security.settings, "JWT_SECRET_KEY", "short")
    security.deployment_safety_check()  # must not raise


# ── secrets_loader ───────────────────────────────────────────────────────────

def test_missing_infisical_environment_refuses_to_start(monkeypatch):
    monkeypatch.setenv("INFISICAL_CLIENT_ID", "x")
    monkeypatch.setenv("INFISICAL_CLIENT_SECRET", "x")
    monkeypatch.setenv("INFISICAL_PROJECT_ID", "x")
    monkeypatch.delenv("INFISICAL_ENVIRONMENT", raising=False)
    with pytest.raises(RuntimeError, match="INFISICAL_ENVIRONMENT"):
        load_secrets_from_infisical()