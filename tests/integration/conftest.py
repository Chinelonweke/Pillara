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

# ─── RAG PIPELINE FIXTURE ─────────────────────────────────────────────────────
# Required by tests/integration/test_rag_pipeline.py
#
# SETUP REQUIREMENTS:
# 1. ChromaDB must be running (docker-compose up -d chromadb)
# 2. Redis must be running (docker-compose up -d redis)
# 3. Run seed script first: python scripts/seed_drug_data.py --drugs warfarin ibuprofen aspirin
#
# The fixture uses the production ChromaDB collection.
# Tests that require seeded data are marked with @pytest.mark.requires_seeded_data.
# CI runs these only when the integration test suite is explicitly triggered.

@pytest_asyncio.fixture(scope="session")
async def rag_pipeline():
    """
    Real RAGPipeline instance connected to live ChromaDB and Redis.
    Requires services to be running and ChromaDB to be seeded.
    """
    from core.config import settings
    from core.redis_client import get_redis

    # Warn loudly if services are not available rather than silently skipping
    redis_client = None
    try:
        redis_client = await get_redis()
        await redis_client.ping()
    except Exception as e:
        pytest.skip(
            f"Redis not available for integration tests: {e}. "
            f"Start with: docker-compose up -d redis"
        )

    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        chroma = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        chroma.heartbeat()
    except Exception as e:
        pytest.skip(
            f"ChromaDB not available for integration tests: {e}. "
            f"Start with: docker-compose up -d chromadb"
        )

    try:
        from ai.rag.pipeline import RAGPipeline
        pipeline = RAGPipeline(redis=redis_client)
        # __init__ handles all setup synchronously — no initialize() needed
    except Exception as e:
        pytest.fail(
            f"RAGPipeline failed to initialize: {e}. "
            f"This is a hard failure — pipeline initialization must succeed."
        )

    yield pipeline

    if redis_client:
        await redis_client.aclose()
         # Reset the module-level Redis singleton to None so later tests in the
        # same pytest process don't receive a closed connection.
        import core.redis_client as _rc
        _rc._redis_client = None