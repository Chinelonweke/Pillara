# tests/unit/conftest.py
#
# Unit test fixtures — NO external services required.
# Run with: pytest tests/unit -q
# Must pass without any database, Redis, or ChromaDB running.
#
# WHY WE SET ENV VARS HERE:
# core/config.py instantiates Settings() at module level.
# Settings() requires DATABASE_URL, REDIS_URL, JWT_SECRET_KEY, GROQ_API_KEY.
# Without them, even importing core.config raises a ValidationError before
# any test runs. We set dummy values here so the module loads cleanly.
# No real services are contacted — the values are never used in unit tests.

import os
import asyncio
import pytest

# Set required env vars before any app code is imported.
# These are dummy values — no real services are contacted in unit tests.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-characters-long")
os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("USE_INFISICAL", "false")


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the entire unit test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()