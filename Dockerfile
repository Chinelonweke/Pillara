# Dockerfile
#
# WHY MULTI-STAGE BUILD:
# Stage 1 (builder): installs ALL dependencies including build tools
# Stage 2 (runtime): copies ONLY what's needed to run — not build tools
#
# Result:
# Single-stage build: ~2.5GB (all dev tools included)
# Multi-stage build:  ~800MB (only runtime dependencies)
#
# Smaller image = faster deployment, less attack surface, less storage cost.
#
# WHY python:3.12-slim (not alpine):
# Alpine uses musl libc, not glibc.
# Some Python packages (numpy, torch, asyncpg) require glibc.
# Using Alpine with these packages means compiling from source — slow, unreliable.
# python:3.12-slim = Debian slim with glibc — smaller than full Debian, compatible.

# ─── STAGE 1: BUILDER ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Set environment variables that affect Python behavior
ENV PYTHONDONTWRITEBYTECODE=1
# PYTHONDONTWRITEBYTECODE: don't create .pyc compiled bytecode files
# WHY: .pyc files are irrelevant in Docker — we never run the same container twice.
# Skip creating them = faster startup, less disk I/O.

ENV PYTHONUNBUFFERED=1
# PYTHONUNBUFFERED: don't buffer stdout/stderr
# WHY: in Docker, buffered output means logs appear in batches or not at all.
# Unbuffered = logs appear immediately as the app writes them.
# Critical for debugging — you see what happened in real time.

# Install system dependencies required for compiling Python packages
RUN apt-get update && apt-get install -y \
    build-essential \
    # gcc, g++, make — required for compiling C extensions (cryptography, bcrypt)
    libpq-dev \
    # PostgreSQL development headers — required by asyncpg
    libffi-dev \
    # Foreign Function Interface — required by cryptography package
    curl \
    # For health checks and downloading files during build
    && rm -rf /var/lib/apt/lists/*
    # WHY CLEAN apt CACHE: significantly reduces image layer size
    # The package list cache isn't needed after installation

# Set working directory for the build stage
WORKDIR /build

# Copy requirements FIRST, before copying the application code
# WHY: Docker layer caching. If requirements.txt hasn't changed, Docker
# uses the cached layer. Only if requirements.txt changes does Docker
# re-run pip install. This makes rebuilds fast when you only changed code.
COPY requirements.txt .

# Install Python dependencies into a dedicated directory
RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
    # --no-cache-dir: don't cache downloaded packages
    # WHY: cached packages take space in the image but are never reused.
    # In production Docker, each build downloads fresh — no cache benefit.
    --prefix=/install \
    # --prefix=/install: install into /install instead of system Python
    # This makes it easy to copy JUST the packages to the runtime stage
    -r requirements.txt


# ─── STAGE 2: RUNTIME ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install ONLY runtime system dependencies (no build tools)
RUN apt-get update && apt-get install -y \
    libpq5 \
    # libpq5: PostgreSQL client library (runtime — no dev headers needed)
    ffmpeg \
    # ffmpeg: required by Whisper for audio processing (converting audio formats)
    curl \
    # Used by Docker healthcheck (CMD below)
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local
# This copies all pip-installed packages from /build/install to /usr/local
# where Python automatically finds them

# Create a non-root user to run the application
# WHY NOT ROOT: running as root in Docker = if the app is compromised,
# the attacker has root access to everything in the container.
# Running as a restricted user limits the blast radius.
RUN groupadd -r pillara && useradd -r -g pillara pillara
# groupadd -r: create system group
# useradd -r: create system user (no login shell, no home directory)
# -g pillara: assign to the pillara group

# Create application directory
WORKDIR /app

# Create directories the app needs, with correct permissions
RUN mkdir -p /tmp/reports /app/logs && \
    chown -R pillara:pillara /app /tmp/reports
# chown -R: change ownership recursively to our pillara user

# Copy application code
# We copy the app LAST so that code changes don't invalidate the
# requirements.txt cache layer (which takes the longest to build)
COPY --chown=pillara:pillara . .
# --chown: file ownership = pillara user (not root)

# Switch to the non-root user
USER pillara

# Document what port the app listens on
# (This is documentation only — doesn't actually publish the port)
EXPOSE 8000

# Healthcheck — Docker can automatically restart unhealthy containers
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
# interval: check every 30 seconds
# timeout: fail if check takes more than 10 seconds
# start-period: wait 60 seconds before first check (app startup time)
# retries: mark unhealthy after 3 consecutive failures

# Run the app with uvicorn
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--loop", "uvloop", \
     "--http", "httptools"]
# main:app = "in main.py, the 'app' object"
# --host 0.0.0.0 = listen on all network interfaces (not just localhost)
# WHY 0.0.0.0: in Docker, localhost only = inside the container.
#              0.0.0.0 = accessible from outside the container.
# --workers 2 = 2 worker processes
#   WHY 2: more workers = better CPU utilization.
#   Formula: 2 × (CPU cores) + 1. Our EC2 t3.micro has 2 vCPUs → 2 workers.
#   Don't use --reload in production (--reload = development mode)
# --loop uvloop = use uvloop instead of default asyncio event loop
#   WHY: uvloop is 2-4x faster than the default asyncio event loop
# --http httptools = use httptools for HTTP parsing
#   WHY: httptools is faster than the default h11 parser