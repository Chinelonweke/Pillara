# core/database.py
# SECURITY/RELIABILITY UPDATES FROM AUDIT:
# 1. pool_timeout=30 — fail fast when pool is exhausted (no infinite hang)
# 2. pool_timeout prevents request 31 hanging forever when 30 connections are busy
# 3. ChromaDB startup retry with tenacity exponential backoff
# 4. Explicit connect_args for SSL enforcement in production

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from core.config import settings
from monitoring.logger import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    pass


def _create_engine() -> AsyncEngine:
    # Build connect_args — SSL in production
    connect_args = {}
    if settings.is_production:
        # Enforce SSL in production — data in transit must be encrypted
        # NeonDB and most managed PostgreSQL providers require this
        connect_args["ssl"] = "require"

    engine = create_async_engine(
        settings.database_url_async,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,

        # RELIABILITY FIX: fail fast when pool is exhausted
        # Without this, request 31 hangs indefinitely waiting for a connection.
        # With this, it raises OperationalError after 30 seconds — caught by error handler.
        pool_timeout=30,

        pool_pre_ping=True,
        pool_recycle=3600,
        connect_args=connect_args,
        echo=settings.DEBUG and settings.ENVIRONMENT == "development",
        future=True,
    )
    return engine


engine: AsyncEngine = _create_engine()

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_health() -> dict:
    start = time.monotonic()
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "healthy", "response_time_ms": round((time.monotonic() - start) * 1000, 2)}
    except Exception as error:
        return {"status": "unhealthy", "error": str(error)}


async def init_database() -> None:
    health = await check_database_health()
    if health["status"] == "healthy":
        logger.info("database_connected", response_time_ms=health["response_time_ms"])
    else:
        logger.error("database_connection_failed", error=health.get("error"))
        raise RuntimeError(f"Cannot connect to database at startup: {health.get('error')}")


async def close_database() -> None:
    await engine.dispose()
    logger.info("database_connections_closed")


# ─── CHROMADB STARTUP WITH RETRY ──────────────────────────────────────────────
# RELIABILITY FIX: ChromaDB container may still be initialising when the app starts.
# Without retry, the first request crashes. With tenacity, we back off and try again.

async def init_chromadb_with_retry() -> None:
    """
    Verifies ChromaDB is reachable at startup, with exponential backoff retry.

    WHY RETRY AT STARTUP (not per-request):
    We want to know ChromaDB is healthy before serving any traffic.
    Per-request retry would hide a broken ChromaDB — the app starts,
    users get errors, and you only discover it when someone complains.
    Startup retry fails loud and fast if ChromaDB never comes up.
    """
    from tenacity import (
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential,
    )
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    @retry(
        stop=stop_after_attempt(5),
        # Try 5 times total before giving up
        wait=wait_exponential(multiplier=1, min=2, max=10),
        # Wait 2s, 4s, 8s, 10s, 10s between retries
        retry=retry_if_exception_type(Exception),
        reraise=True,
        # If all retries fail, re-raise the last exception
    )
    def _connect():
        client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        client.heartbeat()
        return client

    try:
        import asyncio
        await asyncio.to_thread(_connect)
        logger.info("chromadb_connected", host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)
    except Exception as error:
        logger.error("chromadb_connection_failed", error=str(error))
        raise RuntimeError(f"ChromaDB unreachable after 5 retries: {error}")