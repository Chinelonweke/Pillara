# tests/unit/conftest.py
#
# Unit test fixtures — NO external services required.
# Run with: pytest tests/unit -q
# Must pass without any database, Redis, or ChromaDB running.

import asyncio
import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the entire unit test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()