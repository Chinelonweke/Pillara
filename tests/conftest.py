# tests/conftest.py
#
# Pytest fixtures — shared setup for all tests.
# Each test gets a clean database state via transaction rollback.
# No test data leaks between tests.

import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app
from core.database import AsyncSessionFactory, Base, engine


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    """Create all database tables once before the test session."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    """HTTP test client — each test gets a fresh client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


@pytest_asyncio.fixture
async def registered_user(client: AsyncClient) -> dict:
    """Creates a registered user and returns their credentials."""
    import uuid
    email = f"user_{uuid.uuid4().hex[:8]}@test.com"
    password = "TestPass123!"

    response = await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": password,
    })
    assert response.status_code == 201

    return {
        "email": email,
        "password": password,
        "access_token": response.json()["access_token"],
        "refresh_token": response.json()["refresh_token"],
    }


@pytest_asyncio.fixture
async def auth_headers(registered_user: dict) -> dict:
    """Authorization headers for the registered user."""
    return {"Authorization": f"Bearer {registered_user['access_token']}"}


@pytest_asyncio.fixture
async def user_a_headers(client: AsyncClient) -> dict:
    """Auth headers for User A (for IDOR tests)."""
    import uuid
    response = await client.post("/api/v1/auth/register", json={
        "email": f"user_a_{uuid.uuid4().hex[:8]}@test.com",
        "password": "TestPass123!",
    })
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest_asyncio.fixture
async def user_b_profile_id(client: AsyncClient) -> str:
    """Creates User B and returns their profile ID (for IDOR tests)."""
    import uuid
    response = await client.post("/api/v1/auth/register", json={
        "email": f"user_b_{uuid.uuid4().hex[:8]}@test.com",
        "password": "TestPass123!",
    })
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    profiles = await client.get("/api/v1/profiles/", headers=headers)
    return profiles.json()[0]["id"]


@pytest_asyncio.fixture
async def user_b_medication_id(client: AsyncClient, user_b_profile_id: str) -> str:
    """Creates a medication for User B and returns its ID (for IDOR tests)."""
    import uuid
    response = await client.post("/api/v1/auth/register", json={
        "email": f"user_b2_{uuid.uuid4().hex[:8]}@test.com",
        "password": "TestPass123!",
    })
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    med_response = await client.post(
        f"/api/v1/medications/?profile_id={user_b_profile_id}",
        headers=headers,
        json={"name": "Ibuprofen"},
    )
    return med_response.json()["id"]


@pytest_asyncio.fixture
async def rag_pipeline():
    """
    RAG pipeline instance for testing.
    Requires ChromaDB to be running (docker-compose up -d).
    """
    from ai.rag.pipeline import RAGPipeline
    pipeline = RAGPipeline(redis=None)
    yield pipeline