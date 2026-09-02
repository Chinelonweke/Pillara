# tests/integration/conftest.py
#
# Integration test fixtures — requires PostgreSQL, Redis, ChromaDB.
# Run with: pytest tests/integration -q
# Ensure services are running first: docker-compose up -d

import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app
from core.database import AsyncSessionFactory, Base, engine


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the entire integration test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    """Create all database tables once before integration tests run."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    """Database session — rolls back after each test to keep tests isolated."""
    async with AsyncSessionFactory() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest_asyncio.fixture
async def client():
    """HTTP test client — each test gets a fresh client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c