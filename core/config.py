# core/config.py
#
# WHY THIS FILE EXISTS:
# Every setting Pillara needs lives here in one place.
# If DATABASE_URL is missing, the app refuses to start with a clear error.
# This is better than crashing deep inside a database call with a confusing message.
#
# HOW PYDANTIC SETTINGS WORKS:
# BaseSettings automatically reads from environment variables.
# If DATABASE_URL is set in the environment, Pydantic finds it and validates its type.
# If it's missing and has no default, Pydantic raises a clear error at startup.
#
# SECRETS STRATEGY — INFISICAL (NOT .env IN PRODUCTION):
# In development, a local .env file is fine — it's gitignored, never leaves your machine.
# In production, we do NOT use .env at all. Instead, Infisical (open source, free tier)
# injects secrets as environment variables before Settings() reads them.
# This file never imports or talks to Infisical directly — that separation matters.
# Settings() only ever reads from os.environ. WHERE those env vars came from
# (a .env file locally, or Infisical in production) is handled by
# core/secrets_loader.py and the app's startup sequence. Settings stays simple
# and testable — it has no idea Infisical exists.

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    All application settings in one class.

    WHY A CLASS:
    Groups related configuration together.
    Accessed as: settings.DATABASE_URL — clean and readable.
    Type-safe: settings.DEBUG is always a bool, never a string "true".

    WHY INHERIT FROM BaseSettings:
    Gets automatic environment variable reading and validation.
    We declare WHAT we need — BaseSettings handles HOW to find it.
    """

    # ── APP ───────────────────────────────────────────────────────────────────
    APP_NAME: str = "Pillara"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # ── DATABASE ──────────────────────────────────────────────────────────────
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # ── REDIS ─────────────────────────────────────────────────────────────────
    REDIS_URL: str
    REDIS_SESSION_TTL: int = 86400
    REDIS_CACHE_TTL: int = 3600

    # ── SECURITY ──────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    # ── LLM PROVIDERS ─────────────────────────────────────────────────────────
    GROQ_API_KEY: str
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    CEREBRAS_API_KEY: Optional[str] = None
    CEREBRAS_BASE_URL: str = "https://api.cerebras.ai/v1"

    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_SITE_URL: str = "https://pillara.site"
    OPENROUTER_SITE_NAME: str = "Pillara"

    TOGETHER_API_KEY: Optional[str] = None
    TOGETHER_BASE_URL: str = "https://api.together.xyz/v1"

    HUGGINGFACE_API_KEY: Optional[str] = None
    HUGGINGFACE_BASE_URL: str = "https://api-inference.huggingface.co/models"

    LLM_MAX_TOKENS: int = 1024
    LLM_TEMPERATURE: float = 0.1
    LLM_TIMEOUT_SECONDS: int = 30
    LLM_PROVIDER_HEALTH_CACHE_TTL: int = 60
    LLM_REQUESTS_PER_USER_PER_HOUR: int = 20
    LLM_REQUESTS_PER_USER_PER_DAY: int = 100

    # ── RAG ───────────────────────────────────────────────────────────────────
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    CHROMA_COLLECTION_NAME: str = "drug_knowledge"
    RAG_CONFIDENCE_THRESHOLD: float = 0.75
    RAG_TOP_K_RESULTS: int = 5
    RAG_CHUNK_SIZE: int = 400
    RAG_CHUNK_OVERLAP: int = 80
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ── FDA API ───────────────────────────────────────────────────────────────
    FDA_API_KEY: Optional[str] = None
    FDA_API_BASE_URL: str = "https://api.fda.gov/drug"
    FDA_API_TIMEOUT: int = 10

    # ── DRUG TAXONOMY APIs (RxNorm + MedRT) ────────────────────────────────────
    RXNORM_API_BASE_URL: str = "https://rxnav.nlm.nih.gov/REST"
    RXNORM_API_TIMEOUT: int = 5

    # ── RATE LIMITING ─────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000
    AUTH_RATE_LIMIT_PER_MINUTE: int = 5

    # ── NOTIFICATIONS ─────────────────────────────────────────────────────────
    RESEND_API_KEY: Optional[str] = None
    FROM_EMAIL: str = "noreply@pillara.site"          
    ALERT_EMAIL: str = "Nwekechinelo25@yahoo.com"     
    FRONTEND_URL: str = "http://localhost:3000"

    VAPID_PUBLIC_KEY: Optional[str] = None
    VAPID_PRIVATE_KEY: Optional[str] = None
    VAPID_EMAIL: str = "mailto:admin@pillara.app"
    AT_USERNAME: Optional[str] = None
    AT_API_KEY: Optional[str] = None

    # ── MONITORING ────────────────────────────────────────────────────────────
    SENTRY_DSN: Optional[str] = None
    SENTRY_TRACES_SAMPLE_RATE: float = 1.0
    POSTHOG_API_KEY: Optional[str] = None

    # ── STORAGE ───────────────────────────────────────────────────────────────
    PDF_STORAGE_PATH: str = "/tmp/reports"
    MAX_AUDIO_FILE_SIZE_MB: int = 25

    # ── SECRETS MANAGEMENT (INFISICAL) ────────────────────────────────────────
    USE_INFISICAL: bool = False
    INFISICAL_PROJECT_ID: Optional[str] = None
    INFISICAL_ENVIRONMENT: str = "dev"
    INFISICAL_CLIENT_ID: Optional[str] = None
    INFISICAL_CLIENT_SECRET: Optional[str] = None
    INFISICAL_SITE_URL: str = "https://app.infisical.com"

    # ── CORS ──────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://pillara.site",
        "https://www.pillara.site",
    ]
    VAPID_EMAIL: str = "mailto:noreply@pillara.site"

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        allowed = ["development", "staging", "production"]
        if value not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}, got '{value}'")
        return value

    @field_validator("RAG_CONFIDENCE_THRESHOLD")
    @classmethod
    def validate_confidence_threshold(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("RAG_CONFIDENCE_THRESHOLD must be between 0.0 and 1.0")
        return value

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def database_url_async(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    from dotenv import load_dotenv
    load_dotenv()

    if os.getenv("USE_INFISICAL", "false").lower() == "true":
        from core.secrets_loader import load_secrets_from_infisical
        load_secrets_from_infisical()

    return Settings()


# Single shared instance — import this everywhere
settings = get_settings()