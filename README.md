# Pillara

AI-powered medication safety platform for patients, caregivers, and healthcare workers. Checks drug interactions, flags allergy cross-reactivity, sends medication reminders, and answers clinical questions — all grounded in verified drug knowledge.

**Live:** [pillara.site](https://pillara.site) · **API:** [api.pillara.site](https://api.pillara.site)

---

## What It Does

- **Drug interaction checking** — checks any combination of medications against a RAG pipeline of clinical drug knowledge, with deterministic allergy cross-reactivity detection (3-layer: local map → RxNorm → MedRT)
- **AI medication assistant** — answers drug safety questions grounded in retrieved clinical context, with a confidence gate that refuses to answer if retrieval score is below 0.75
- **Medication reminders** — daily/weekly/one-time email reminders via ARQ background worker
- **Multi-patient profiles** — caregivers manage family members, nurses access patient charts, parents track children's prescriptions
- **Role-based sharing** — owner → caregiver → viewer hierarchy with invite/claim flows

---

## Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI (async) |
| Database | NeonDB (PostgreSQL + asyncpg) |
| Cache / Sessions | Redis |
| Vector DB | ChromaDB |
| AI Providers | Groq → Cerebras → OpenRouter → Together AI → HuggingFace |
| Email | Resend |
| Background jobs | ARQ |
| Monitoring | Prometheus + Grafana + PostHog + Sentry |
| Frontend | Next.js (Vercel) |
| Secrets | Infisical |
| DNS | Cloudflare |

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- Docker Desktop
- Node.js 18+
- Git

### 1. Clone and install

```bash
git clone https://github.com/Chinelonweke/Pillara.git
cd Pillara
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac/Linux
pip install -r requirements.txt
```

### 2. Configure secrets

```bash
cp .env.example .env
```

Fill in `.env` with your API keys. All secrets are documented in `.env.example`.

Alternatively, configure Infisical:
- Set `USE_INFISICAL=true` in `.env`
- Add your Infisical project credentials

### 3. Start infrastructure

```bash
docker-compose up -d
```

This starts: Redis, ChromaDB, Prometheus, Grafana.

### 4. Run database migrations

```bash
alembic upgrade head
```

### 5. Seed drug knowledge base

```bash
python scripts/seed_drug_knowledge.py
```

Embeds 541 drug knowledge chunks into ChromaDB. Only needed once — data persists in the Docker volume.

### 6. Start the application

```bash
# Terminal 1 — API server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — Background worker (reminders)
arq workers.worker.WorkerSettings

# Terminal 3 — Frontend
cd pillara-web
npm install
npm run dev
```

- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Frontend: http://localhost:3000
- Grafana: http://localhost:3001 
- Prometheus: http://localhost:9090

---

## Project Structure

```
core/               — config, database, security, redis, exceptions
api/
  routers/          — auth, profiles, sharing, medications, interactions, ai, reminders
  middleware.py     — request context, security headers
  dependencies.py   — auth, rate limiting, IDOR guards
services/           — business logic (auth, profiles, medications, sharing, reminders, email)
models/             — SQLAlchemy ORM models (User, Profile, Medication, Reminder, ProfileAccess)
schemas/            — Pydantic request/response validation
ai/
  llm/              — multi-provider LLM client with 5-provider fallback chain
  rag/              — RAG pipeline (embed, retrieve, rerank, confidence gate)
workers/            — ARQ background jobs (medication reminders)
monitoring/
  logger.py         — structured JSON logging with PHI scrubbing
  audit.py          — HIPAA audit trail
  analytics.py      — PostHog product analytics
  sentry_setup.py   — Sentry error tracking with PHI scrubbing
alembic/            — database migrations
scripts/            — seed scripts
tests/              — unit and integration tests
pillara-web/        — Next.js frontend
grafana/            — Grafana dashboard provisioning
prometheus.yml      — Prometheus scrape config
```

---

## Security Architecture

**Authentication**
- JWT access tokens (30 min) + refresh tokens (7 days) with rotation
- Silent token refresh on 401 — users stay logged in without interruption
- Refresh token reuse detection — stolen token triggers full session revocation
- Account lockout after 5 failed login attempts (15 min lockout)
- All sessions revoked immediately on password reset

**Authorization**
- IDOR protection — every query filters by authenticated user ID
- Role-based sharing — owner / caregiver / viewer with permission enforcement
- Email verification gate on safety-critical endpoints

**Rate Limiting**
- Auth endpoints: 5 requests/minute per IP+email
- API endpoints: 60 requests/minute per user
- LLM endpoints: 20 requests/hour, 100/day per user

**AI Safety**
- Confidence gate — refuses to answer drug safety questions below 0.75 similarity score
- Allergy cross-reactivity is deterministic (not LLM-based) — local class map → RxNorm → MedRT
- Prompt injection prevention — NFKD normalization + pattern matching
- XSS prevention — HTML stripped from all LLM output server-side

**Data Protection**
- PHI scrubbed from logs and Sentry before leaving server
- IP addresses SHA-256 hashed — never stored raw
- HIPAA audit trail — every PHI access logged with user ID, timestamp, outcome
- Refresh tokens stored as JTI references — never plaintext

---

## API Overview

```
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
POST /api/v1/auth/refresh
POST /api/v1/auth/password-reset/request
POST /api/v1/auth/password-reset/confirm
POST /api/v1/auth/resend-verification

GET  /api/v1/profiles/
POST /api/v1/profiles/

GET  /api/v1/sharing/all
POST /api/v1/sharing/{id}/invite
POST /api/v1/sharing/{id}/send-claim-invite
POST /api/v1/sharing/accept-invite
POST /api/v1/sharing/claim

GET  /api/v1/medications/?profile_id=
POST /api/v1/medications/?profile_id=
DELETE /api/v1/medications/{id}

POST /api/v1/interactions/check
POST /api/v1/ai/query
POST /api/v1/ai/feedback

GET  /api/v1/reminders/?profile_id=
POST /api/v1/reminders/?profile_id=
DELETE /api/v1/reminders/{id}

GET  /health
GET  /metrics
```

---

## Monitoring

| Tool | Purpose | URL |
|------|---------|-----|
| UptimeRobot | Server uptime alerts | External |
| Prometheus | Metrics collection | /metrics |
| Grafana | Metrics visualisation | :3001 |
| Sentry | Error tracking | sentry.io |
| PostHog | Product analytics | app.posthog.com |
| Structured logs | Request/audit trail | stdout → DigitalOcean |

---

## Deployment

**Backend:** DigitalOcean Droplet ($12/mo) + Docker + Nginx + Let's Encrypt

**Frontend:** Vercel (free tier)

**Database:** NeonDB (serverless PostgreSQL — free tier)

**Environment variables for production:** Set in Infisical production environment.

**Required steps on first deployment:**
```bash
alembic upgrade head                    # run migrations on production NeonDB
python scripts/seed_drug_knowledge.py   # seed ChromaDB with drug knowledge
```

---

## Development Notes

- `models/` contains SQLAlchemy models — required for app startup
- ChromaDB data persists in Docker volume `pillara_chromadb_data` — do not delete
- ARQ worker must run as a separate process alongside FastAPI
- NeonDB free tier sleeps after 5 min idle — keep-alive ping runs every 4 min
- Cross-encoder model cached after first request — first AI query is slow (~15s), subsequent queries ~5s