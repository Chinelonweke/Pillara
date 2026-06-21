# Pillara

AI-powered medication safety platform — drug interaction checking, smart reminders, and voice-first health insights.

## Stack

FastAPI · PostgreSQL (async) · Redis · ChromaDB · 5-provider LLM fallback (Groq, Cerebras, OpenRouter, Together AI, HuggingFace) · Whisper STT · Coqui TTS

## Setup

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install --upgrade pip
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in real API keys.

```bash
docker-compose up -d           # starts PostgreSQL, Redis, ChromaDB
alembic upgrade head           # run database migrations
python scripts/seed_drug_data.py   # seed initial drug knowledge base
```

## Running

```bash
uvicorn main:app --reload                          # API server
arq workers.worker.WorkerSettings                   # background worker (separate terminal)
```

API docs available at `http://localhost:8000/docs` in development.

## Testing

```bash
pytest                          # all tests
pytest tests/unit               # fast unit tests only
pytest tests/integration        # full integration tests (requires running services)
pytest -m security              # security-critical tests only
pytest --cov=. --cov-report=html  # coverage report
```

## Security Architecture

- **IDOR protection**: every database query for user-owned resources filters by both resource ID and the authenticated user's ID, enforced at the service layer via `_ownership_query` patterns
- **Mass assignment protection**: update schemas explicitly exclude `id`, `user_id`, `profile_id` fields
- **Refresh token reuse detection**: stolen refresh tokens trigger full session revocation
- **Account lockout**: 5 failed login attempts locks the account for 15 minutes
- **Rate limiting**: by `user_id` for authenticated endpoints (IPv6-proof), by combined `ip_hash:email` for auth endpoints
- **Confidence gate**: AI never answers drug safety questions below a 0.75 similarity threshold — returns a safe fallback instead of guessing
- **PHI scrubbing**: structured logging automatically redacts medication names, emails, and other PHI fields before they're written
- **HIPAA audit trail**: every PHI access is logged with user ID, timestamp, and outcome — retained for 6 years

## Project Structure

```
core/        — config, database, security, redis, exceptions
api/         — routers, middleware, dependencies (auth + IDOR guards)
services/    — business logic, audit logging
models/      — SQLAlchemy ORM models
schemas/     — Pydantic request/response validation
ai/llm/      — multi-provider LLM client with fallback chain
ai/rag/      — retrieval pipeline, chunking, embeddings
ai/stt/tts/  — local Whisper and Coqui TTS clients
workers/     — ARQ background jobs (reminders)
monitoring/  — structured logging, audit trail, Sentry, Prometheus metrics
tests/       — unit and integration tests
```