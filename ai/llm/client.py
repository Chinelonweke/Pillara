# ai/llm/client.py
#
# WHY THIS FILE IS THE HEART OF PILLARA'S AI LAYER:
# This file implements the 5-provider fallback chain.
# Every AI response in Pillara — drug interactions, medication info,
# health insights, voice responses — flows through this one file.
#
# THE 5 PROVIDERS IN ORDER:
# 1. Groq          → fastest, 14,400 free req/day
# 2. Cerebras      → different hardware, 21,600 free req/day
# 3. OpenRouter    → 4 free models inside, auto-routes between 50+ providers
# 4. Together AI   → reliable burst capacity, $1 free credit
# 5. HuggingFace   → always free, always slow, always available
#
# WHY EACH PROVIDER HAS ITS OWN TIMEOUT:
# If Groq is having issues, we want to know QUICKLY so we can
# try the next provider. We give Groq 8 seconds — generous enough
# for a normal response, short enough to fail fast if it's down.
# HuggingFace gets 30 seconds because it's slow but reliable.
#
# THE PROVIDER HEALTH CACHE:
# When Groq fails with a rate limit, we mark it as "unhealthy" in Redis
# for 60 seconds. The next request skips Groq immediately instead of
# wasting 8 seconds finding out it's still rate limited.
# This makes the fallback chain fast in practice, not just in theory.

import asyncio
import time
from enum import Enum
from typing import Any, Optional

import httpx
from openai import AsyncOpenAI  # OpenAI-compatible client used for multiple providers

from core.config import settings
from monitoring.logger import get_logger

logger = get_logger(__name__)


# ─── QUERY COMPLEXITY ENUM ────────────────────────────────────────────────────
#
# WHY AN ENUM FOR COMPLEXITY:
# We use two different model sizes:
# - 70B (large, powerful) for complex medical reasoning
# - 8B (small, fast) for simple factual questions
#
# Using an Enum prevents typos: QueryComplexity.SIMPLE is safer than "simple"
# which could be mistyped as "simle" or "Simple" silently.

class QueryComplexity(str, Enum):
    """
    Determines which model size to use.
    SIMPLE → 8B models (faster, cheaper, good for basic info)
    COMPLEX → 70B models (slower, more capable, required for drug safety)
    """
    SIMPLE = "simple"
    COMPLEX = "complex"


# ─── PROVIDER CONFIGURATION ───────────────────────────────────────────────────
#
# WHY A LIST OF DICTS (not a class per provider):
# Each provider has the same shape of configuration.
# A list of dicts is simpler and easier to iterate over.
# We loop through the list in order — the loop IS the fallback logic.
#
# WHY ORDER MATTERS:
# The list order defines the fallback order.
# index 0 = try first, index 4 = try last.
# Changing the fallback order = reordering this list.

PROVIDER_CONFIGS: list = [
    {
        "name": "groq",
        "priority": 1,
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_setting": "GROQ_API_KEY",
        "models": {
            QueryComplexity.COMPLEX: "llama-3.3-70b-versatile",
            QueryComplexity.SIMPLE:  "llama-3.1-8b-instant",
        },
        "timeout_seconds": 8,
        "extra_headers": {},
    },
    {
        "name": "cerebras",
        "priority": 2,
        "base_url": "https://api.cerebras.ai/v1",
        "api_key_setting": "CEREBRAS_API_KEY",
        "models": {
            QueryComplexity.COMPLEX: "llama3.1-70b",
            QueryComplexity.SIMPLE:  "llama3.1-8b",
        },
        "timeout_seconds": 10,
        "extra_headers": {},
    },
    {
        "name": "openrouter",
        "priority": 3,
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_setting": "OPENROUTER_API_KEY",
        "models": {
            QueryComplexity.COMPLEX: [
                "meta-llama/llama-3.3-70b-instruct:free",
                "meta-llama/llama-3.1-8b-instruct:free",
                "mistralai/mistral-7b-instruct:free",
                "google/gemma-3-27b-it:free",
            ],
            QueryComplexity.SIMPLE: [
                "meta-llama/llama-3.1-8b-instruct:free",
                "mistralai/mistral-7b-instruct:free",
                "google/gemma-3-27b-it:free",
            ],
        },
        "timeout_seconds": 15,
        "extra_headers": {
            "HTTP-Referer": settings.OPENROUTER_SITE_URL,
            "X-Title": settings.OPENROUTER_SITE_NAME,
        },
    },
    {
        "name": "together",
        "priority": 4,
        "base_url": "https://api.together.xyz/v1",
        "api_key_setting": "TOGETHER_API_KEY",
        "models": {
            QueryComplexity.COMPLEX: "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            QueryComplexity.SIMPLE:  "meta-llama/Llama-3.2-3B-Instruct-Turbo",
        },
        "timeout_seconds": 20,
        "extra_headers": {},
    },
    {
        "name": "huggingface",
        "priority": 5,
        "base_url": "https://api-inference.huggingface.co/models",
        "api_key_setting": "HUGGINGFACE_API_KEY",
        "models": {
            QueryComplexity.COMPLEX: "meta-llama/Llama-3.1-70B-Instruct",
            QueryComplexity.SIMPLE:  "meta-llama/Llama-3.2-3B-Instruct",
        },
        "timeout_seconds": 30,
        "extra_headers": {},
    },
]


# ─── LLM CLIENT ───────────────────────────────────────────────────────────────

class LLMClient:
    """
    WHY A CLASS:
    The LLM client needs:
    - Access to Redis (for provider health cache)
    - Configuration (provider list, timeouts)
    - Multiple related methods (call, check health, log usage)
    A class bundles all of this cleanly.

    USAGE:
        llm = LLMClient(redis=redis_client)
        response = await llm.complete(
            messages=[{"role": "user", "content": "Is aspirin safe with warfarin?"}],
            complexity=QueryComplexity.COMPLEX
        )
    """

    def __init__(self, redis=None):
        self.redis = redis
        self._health_key_prefix = "llm_health:"

    def _get_api_key(self, provider_config: dict) -> Optional[str]:
        key_setting_name = provider_config["api_key_setting"]
        api_key = getattr(settings, key_setting_name, None)
        return api_key

    async def _is_provider_healthy(self, provider_name: str) -> bool:
        if not self.redis:
            return True

        try:
            key = f"{self._health_key_prefix}{provider_name}"
            status = await self.redis.get(key)
            return status is None
        except Exception:
            return True

    async def _mark_provider_unhealthy(
        self,
        provider_name: str,
        ttl_seconds: int = None
    ) -> None:
        if not self.redis:
            return

        ttl = ttl_seconds or settings.LLM_PROVIDER_HEALTH_CACHE_TTL

        try:
            key = f"{self._health_key_prefix}{provider_name}"
            await self.redis.setex(key, ttl, "unhealthy")
        except Exception:
            pass

    async def _call_openai_compatible_provider(
        self,
        provider_config: dict,
        model: str,
        messages: list,
        system_prompt: str,
    ) -> str:
        api_key = self._get_api_key(provider_config)
        if not api_key:
            raise ValueError(f"No API key configured for {provider_config['name']}")

        full_messages = [
            {"role": "system", "content": system_prompt}
        ] + messages

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=provider_config["base_url"],
            default_headers=provider_config.get("extra_headers", {}),
            timeout=provider_config["timeout_seconds"],
        )

        start_time = time.monotonic()

        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=full_messages,
                max_tokens=settings.LLM_MAX_TOKENS,
                temperature=settings.LLM_TEMPERATURE,
            ),
            timeout=provider_config["timeout_seconds"]
        )

        latency_ms = (time.monotonic() - start_time) * 1000
        response_text = response.choices[0].message.content

        logger.info(
            "llm_call_success",
            provider=provider_config["name"],
            model=model,
            latency_ms=round(latency_ms, 2),
            prompt_tokens=response.usage.prompt_tokens if response.usage else None,
            completion_tokens=response.usage.completion_tokens if response.usage else None,
        )

        return response_text

    async def _try_openrouter_models(
        self,
        provider_config: dict,
        model_list: list,
        messages: list,
        system_prompt: str,
    ) -> str:
        last_error = None

        for attempt_number, model in enumerate(model_list, start=1):
            try:
                logger.debug(
                    "openrouter_model_attempt",
                    model=model,
                    attempt=attempt_number,
                    total_models=len(model_list)
                )

                result = await self._call_openai_compatible_provider(
                    provider_config=provider_config,
                    model=model,
                    messages=messages,
                    system_prompt=system_prompt,
                )
                return result

            except Exception as error:
                last_error = error
                logger.warning(
                    "openrouter_model_failed",
                    model=model,
                    attempt=attempt_number,
                    error=str(error),
                    error_type=type(error).__name__,
                )

        raise last_error

    async def complete(
        self,
        messages: list,
        system_prompt: str,
        complexity: QueryComplexity = QueryComplexity.COMPLEX,
        request_id: str = "unknown",
    ) -> dict:
        last_error = None
        providers_tried = []

        for provider_config in PROVIDER_CONFIGS:
            provider_name = provider_config["name"]

            api_key = self._get_api_key(provider_config)
            if not api_key:
                logger.debug("provider_skipped_no_key", provider=provider_name)
                continue

            is_healthy = await self._is_provider_healthy(provider_name)
            if not is_healthy:
                logger.debug("provider_skipped_unhealthy", provider=provider_name)
                continue

            providers_tried.append(provider_name)

            try:
                provider_models = provider_config["models"]
                model_for_complexity = provider_models[complexity]

                if isinstance(model_for_complexity, list):
                    response_text = await self._try_openrouter_models(
                        provider_config=provider_config,
                        model_list=model_for_complexity,
                        messages=messages,
                        system_prompt=system_prompt,
                    )
                    model_used = "openrouter_free_model"
                else:
                    response_text = await self._call_openai_compatible_provider(
                        provider_config=provider_config,
                        model=model_for_complexity,
                        messages=messages,
                        system_prompt=system_prompt,
                    )
                    model_used = model_for_complexity

                return {
                    "text": response_text,
                    "provider": provider_name,
                    "model": model_used,
                    "complexity": complexity.value,
                    "fallback_triggered": provider_name != "groq",
                    "providers_tried": providers_tried,
                }

            except asyncio.TimeoutError:
                last_error = Exception(f"Provider {provider_name} timed out")
                logger.warning(
                    "provider_timeout",
                    provider=provider_name,
                    timeout=provider_config["timeout_seconds"],
                    request_id=request_id,
                )
                await self._mark_provider_unhealthy(provider_name, ttl_seconds=30)

            except Exception as error:
                last_error = error
                error_str = str(error).lower()

                if "rate" in error_str or "429" in error_str:
                    unhealthy_ttl = 60
                elif "auth" in error_str or "401" in error_str:
                    unhealthy_ttl = 300
                else:
                    unhealthy_ttl = 30

                logger.warning(
                    "provider_error",
                    provider=provider_name,
                    error=str(error),
                    error_type=type(error).__name__,
                    unhealthy_ttl=unhealthy_ttl,
                    request_id=request_id,
                )
                await self._mark_provider_unhealthy(provider_name, ttl_seconds=unhealthy_ttl)

        # All providers failed
        logger.error(
            "all_providers_failed",
            providers_tried=providers_tried,
            last_error=str(last_error),
            request_id=request_id,
        )

        await self._send_critical_alert(
            f"ALL LLM PROVIDERS FAILED\n"
            f"Providers tried: {providers_tried}\n"
            f"Last error: {last_error}\n"
            f"Request ID: {request_id}"
        )

        from core.exceptions import AIServiceError
        raise AIServiceError(
            "AI service is temporarily unavailable. Please try again in a moment."
        )

    async def _send_critical_alert(self, message: str) -> None:
        """
        Sends an email alert via Resend when all AI providers fail.

        Uses Resend (already configured) so no extra secrets needed.
        Fires and forgets — we don't want a failed alert to block anything.
        """
        if not settings.RESEND_API_KEY:
            return  # Resend not configured — skip silently

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "from": "alerts@pillara.site",
                        "to": ["nwekechinelo25@yahoo.com"],
                        "subject": "🚨 Pillara — All AI Providers Down",
                        "html": f"<h2>🚨 PILLARA CRITICAL ALERT</h2><p>{message}</p>"
                    }
                )
        except Exception as error:
            # If the alert email fails, log it but don't raise
            logger.error("email_alert_failed", error=str(error))

    async def classify_query_complexity(self, query: str) -> QueryComplexity:
        query_lower = query.lower()

        complex_keywords: set = {
            "interact", "interaction", "safe to take", "together",
            "combine", "combination", "side effect", "overdose",
            "dangerous", "risk", "harm", "safe", "avoid",
            "warning", "contraindicated", "allergy", "reaction",
            "dose", "dosage", "how much", "maximum", "minimum"
        }

        has_complex_keyword = any(
            keyword in query_lower
            for keyword in complex_keywords
        )

        if has_complex_keyword:
            return QueryComplexity.COMPLEX

        word_count = len(query.split())
        if word_count > 15:
            return QueryComplexity.COMPLEX

        return QueryComplexity.SIMPLE