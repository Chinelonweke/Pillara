# api/middleware.py
#
# MIDDLEWARE RUNS ON EVERY REQUEST — before the route handler and after.
# Order of execution (innermost to outermost on the way in):
# 1. SecurityHeadersMiddleware   — adds security headers to every response
# 2. RequestContextMiddleware    — assigns request ID, binds logging context
#
# Rate limiting is handled in api/dependencies.py as FastAPI dependencies
# because it needs access to the authenticated user_id for auth'd endpoints.
# Middleware runs before authentication — it cannot know the user_id yet.

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

import structlog

from core.security import hash_ip_address
from monitoring.logger import RequestLogger, get_logger

logger = get_logger(__name__)
request_logger = RequestLogger()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Assigns a unique request ID to every incoming request.
    Binds request_id and ip_hash to the structlog context —
    so every log line written during this request automatically
    includes request_id without any developer having to pass it around.

    WHY REQUEST ID:
    When debugging a specific user complaint, you filter logs by request_id
    and see every log line from that exact request in order.
    Without it, logs from concurrent requests are interleaved and unreadable.

    WHY MIDDLEWARE (not a dependency):
    Dependencies run per-route. Middleware runs on everything including
    404s and OPTIONS preflight requests — we want IDs on all of those too.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate or accept a request ID
        # If the client sends X-Request-ID, use it (useful for frontend tracing)
        # Otherwise generate a new UUID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Get and anonymise the client IP
        # X-Forwarded-For is set by load balancers and reverse proxies
        # It contains the real client IP when behind nginx/cloudflare
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # X-Forwarded-For can be a comma-separated list: "client, proxy1, proxy2"
            # The first value is the original client IP
            raw_ip = forwarded_for.split(",")[0].strip()
        else:
            raw_ip = request.client.host if request.client else "unknown"

        ip_hash = hash_ip_address(raw_ip)

        # Bind to structlog context vars — available for all log calls in this request
        # asynccontextvars are async-safe: each request has its own isolated context
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            ip_hash=ip_hash,
        )

        # Store on request.state so route handlers and dependencies can access them
        request.state.request_id = request_id
        request.state.ip_hash = ip_hash

        start_time = time.monotonic()

        # Call the next middleware or route handler
        response = await call_next(request)

        duration_ms = (time.monotonic() - start_time) * 1000

        # Add request ID to response headers — frontend can log this for correlation
        response.headers["X-Request-ID"] = request_id

        # Log the completed request
        request_logger.log_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
            ip_hash=ip_hash,
        )

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to every HTTP response.

    WHY HEADERS FOR SECURITY:
    These headers instruct browsers on how to handle our content.
    Without them, browsers make permissive assumptions that attackers exploit.

    Each header is explained below with exactly what it prevents.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent browsers from MIME-sniffing the content type
        # Without this: browser sees a .txt file with JS inside and executes it
        # With this: browser trusts the Content-Type header, nothing else
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent this page from being embedded in an iframe on another site
        # Without this: clickjacking — attacker overlays our UI on their malicious page
        # With this: page can only be framed by the same origin (or nowhere)
        response.headers["X-Frame-Options"] = "DENY"

        # Enable browser's built-in XSS filter (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # WHY WE SKIP CSP ON DOCS ROUTES:
        # FastAPI's built-in Swagger UI (/docs) and ReDoc (/redoc) load their
        # JS/CSS/fonts from cdn.jsdelivr.net — they are NOT part of our actual
        # application surface, just a development tool FastAPI generates for
        # us. A strict script-src 'self' / style-src 'self' / font-src 'self'
        # policy (correct and necessary for our REAL pages and API responses)
        # blocks every one of those CDN resources, leaving /docs completely
        # blank. Since /docs, /redoc, and /openapi.json are already disabled
        # entirely in production (see main.py: docs_url=... if ENVIRONMENT ==
        # "development" else None), it's safe to exempt only these three
        # specific, already-dev-only paths from CSP rather than weakening the
        # policy for the application as a whole.
        if request.url.path not in ("/docs", "/redoc", "/openapi.json"):
            # Control which origins can load resources (images, scripts, API calls)
            # default-src 'self': only load resources from our own domain
            # We add specific exceptions for fonts, analytics, etc.
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "connect-src 'self'; "
                "font-src 'self'; "
                "frame-ancestors 'none'"
                # frame-ancestors 'none' = stronger version of X-Frame-Options: DENY
            )

        return response

        # Force HTTPS — tell browsers to only connect via HTTPS for next 1 year
        # max-age=31536000 = 1 year in seconds
        # includeSubDomains = applies to all subdomains too
        # preload = submit to browser HSTS preload lists (highest protection)
        # ONLY set this in production — it would break local HTTP development
        from core.config import settings
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # Control what information is sent in the Referer header
        # strict-origin-when-cross-origin: send full path for same-origin,
        # only origin for cross-origin HTTPS, nothing for HTTP
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict what browser features our app can use
        # Explicitly disable features we don't need — reduces attack surface
        response.headers["Permissions-Policy"] = (
            "camera=(), "          # we don't use the camera
            "microphone=(self), "  # we DO use microphone (voice input)
            "geolocation=(), "     # we don't need location
            "payment=()"           # we don't handle payments directly
        )

        # Remove the Server header — don't advertise what software we're running
        # Knowing "uvicorn/0.32.1" helps attackers find version-specific exploits
        if "server" in response.headers:
            del response.headers["server"]

        return response