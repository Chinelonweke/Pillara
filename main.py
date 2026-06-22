# main.py
# SECURITY UPDATES FROM AUDIT:
# 1. production_safety_check() called at startup — refuses to start with DEBUG=True in prod
# 2. init_chromadb_with_retry() called at startup — verifies ChromaDB before serving traffic
# 3. LLM output stripped of HTML before returning to client (XSS prevention)

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from core.database import close_database, init_database, init_chromadb_with_retry
from core.exceptions import PillaraError, RateLimitError
from core.redis_client import close_redis, init_redis
from core.security import production_safety_check
from monitoring.logger import configure_logging, get_logger
from monitoring.sentry_setup import init_sentry
from schemas.all_schemas import ErrorResponse, HealthCheckResponse

configure_logging()
logger = get_logger(__name__)

# WHY SENTRY INITIALIZES HERE (module level, before lifespan):
# Sentry must be active before ANYTHING else runs — including the lifespan
# startup sequence. If the database connection fails at startup, or if an
# import error occurs in a router, Sentry needs to already be initialized
# to capture it. Initializing inside lifespan would mean startup errors
# before that line are invisible to Sentry entirely.
# init_sentry() is a no-op if SENTRY_DSN is not configured, so this is
# always safe to call unconditionally.
init_sentry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ──────────────────────────────────────────────────────────────
    logger.info("pillara_starting", version=settings.APP_VERSION, environment=settings.ENVIRONMENT)

    # SECURITY FIX: Refuse to start with unsafe production config
    production_safety_check()

    await init_database()
    await init_redis()

    # RELIABILITY FIX: Verify ChromaDB with retry before serving any traffic
    try:
        await init_chromadb_with_retry()
    except RuntimeError as error:
        logger.warning("chromadb_unavailable_at_startup", error=str(error))
        # We warn but don't crash — the app can serve non-AI endpoints even without ChromaDB
        # AI endpoints will fail gracefully if ChromaDB is down

    logger.info("pillara_ready", version=settings.APP_VERSION)
    yield

    # ── SHUTDOWN ─────────────────────────────────────────────────────────────
    logger.info("pillara_shutting_down")
    await close_database()
    await close_redis()
    logger.info("pillara_stopped")


app = FastAPI(
    title="Pillara API",
    description="AI-powered medication safety assistant API",
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT == "development" else None,
    lifespan=lifespan,
)

from api.middleware import RequestContextMiddleware, SecurityHeadersMiddleware

# WHY THESE TWO MIDDLEWARES, AND WHY THIS ORDER:
# Starlette middleware runs as a stack — the LAST one added runs FIRST on
# the way in. We want RequestContextMiddleware to run before anything else,
# since it sets request.state.ip_hash and request.state.request_id, which
# route handlers (like auth.register) depend on existing. SecurityHeadersMiddleware
# adds response headers (CSP, X-Frame-Options, etc.) on the way out, and doesn't
# depend on anything else having run first.
#
# BUG THIS FIXES: both of these classes were fully written in api/middleware.py
# but never actually registered with app.add_middleware() — they existed in the
# codebase but never ran. This caused AttributeError: 'State' object has no
# attribute 'ip_hash' the first time any endpoint depending on it was called
# (e.g. POST /api/v1/auth/register).
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)

# Register routers
try:
    from api.routers import auth, medications, interactions, ai_chat, reminders, profiles, reports
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
    app.include_router(profiles.router, prefix="/api/v1/profiles", tags=["Profiles"])
    app.include_router(medications.router, prefix="/api/v1/medications", tags=["Medications"])
    app.include_router(interactions.router, prefix="/api/v1/interactions", tags=["Drug Interactions"])
    app.include_router(ai_chat.router, prefix="/api/v1/ai", tags=["AI Assistant"])
    app.include_router(reminders.router, prefix="/api/v1/reminders", tags=["Reminders"])
    app.include_router(reports.router, prefix="/api/v1/reports", tags=["Reports"])
except ImportError as import_error:
    logger.warning("some_routers_not_loaded", error=str(import_error))


@app.exception_handler(PillaraError)
async def pillara_error_handler(request: Request, error: PillaraError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content=error.to_dict(),
        headers=({"Retry-After": str(error.retry_after_seconds)} if isinstance(error, RateLimitError) else {}),
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, error: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        error=str(error),
        error_type=type(error).__name__,
        path=request.url.path,
        method=request.method,
    )
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(error)
    except Exception:
        pass

    # SECURITY: Never expose exception details to the client in any environment.
    # The full error is logged internally — the client gets a generic message only.
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "internal_error", "message": "An unexpected error occurred. Our team has been notified."},
    )


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    from core.database import check_database_health

    db_health = await check_database_health()

    try:
        from core.redis_client import get_redis
        redis = await get_redis()
        await redis.ping()
        redis_status = "healthy"
    except Exception as e:
        redis_status = f"unhealthy: {type(e).__name__}"

    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        chroma_client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        chroma_client.heartbeat()
        chroma_status = "healthy"
    except Exception as e:
        chroma_status = f"unhealthy: {type(e).__name__}"

    services = {
        "database": db_health["status"],
        "redis": redis_status,
        "chromadb": chroma_status,
    }
    all_healthy = all(v == "healthy" for v in services.values())

    return {
        "status": "healthy" if all_healthy else "degraded",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "services": services,
    }


@app.get("/metrics", tags=["Monitoring"], include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint — scraped by monitoring infrastructure."""
    from fastapi.responses import Response
    from monitoring.metrics import get_metrics
    from prometheus_client import CONTENT_TYPE_LATEST

    return Response(content=get_metrics(), media_type=CONTENT_TYPE_LATEST)


@app.get("/", tags=["Root"])
async def root() -> dict:
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }