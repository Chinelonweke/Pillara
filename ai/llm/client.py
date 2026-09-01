# ai/llm/client.py
import asyncio
import time
from enum import Enum
from typing import Optional

import httpx
from openai import AsyncOpenAI

from core.config import settings
from monitoring.logger import get_logger

logger = get_logger(__name__)


class QueryComplexity(str, Enum):
    SIMPLE = "simple"
    COMPLEX = "complex"


# Providers tried in order — list order IS the fallback order
PROVIDER_CONFIGS: list = [
    {
        "name": "groq",
        "priority": 1,
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_setting": "GROQ_API_KEY",
        "models": {
            QueryComplexity.COMPLEX: "openai/gpt-oss-20b",
            QueryComplexity.SIMPLE:  "openai/gpt-oss-20b",
        },
        "timeout_seconds": 8,
        "extra_headers": {},
    },

    {
        "name": "gemini",
        "priority": 3,
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "api_key_setting": "GOOGLE_API_KEY",
        "models": {
            QueryComplexity.COMPLEX: [
                "gemini-3.5-flash",
                "gemini-3.1-flash-lite",
                "gemini-flash-lite-latest",
            ],
            QueryComplexity.SIMPLE: [
                "gemini-3.5-flash-lite",
                "gemini-flash-lite-latest",
                "gemini-3.1-flash-lite",
            ],
        },
        "timeout_seconds": 30,
        "extra_headers": {},
        "custom_handler": "gemini",
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


class LLMClient:
    def __init__(self, redis=None):
        self.redis = redis
        self._health_key_prefix = "llm_health:"

    def _get_api_key(self, provider_config: dict) -> Optional[str]:
        return getattr(settings, provider_config["api_key_setting"], None)

    async def _is_provider_healthy(self, provider_name: str) -> bool:
        if not self.redis:
            return True
        try:
            status = await self.redis.get(f"{self._health_key_prefix}{provider_name}")
            return status is None
        except Exception as health_err:
            import logging; logging.getLogger(__name__).debug("provider_health_check_failed", extra={"error": str(health_err)})
            return True

    async def _mark_provider_unhealthy(self, provider_name: str, ttl_seconds: int = None) -> None:
        if not self.redis:
            return
        try:
            ttl = ttl_seconds or settings.LLM_PROVIDER_HEALTH_CACHE_TTL
            await self.redis.setex(f"{self._health_key_prefix}{provider_name}", ttl, "unhealthy")
        except Exception:
            import logging; logging.getLogger(__name__).warning("provider_health_mark_failed", extra={"error": "redis unavailable"})

    async def _call_gemini_provider(self, provider_config: dict, model: str, messages: list, system_prompt: str) -> str:
        """
        Calls Google Gemini API using its native format.
        Gemini uses a different request/response format from OpenAI.
        """
        import httpx

        api_key = self._get_api_key(provider_config)
        if not api_key:
            raise ValueError("No API key configured for gemini")

        # Convert OpenAI message format to Gemini format
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })

        # Add system prompt as first user message if provided
        if system_prompt:
            contents.insert(0, {
                "role": "user",
                "parts": [{"text": f"System instructions: {system_prompt}"}]
            })
            contents.insert(1, {
                "role": "model",
                "parts": [{"text": "Understood. I will follow these instructions."}]
            })

        url = f"{provider_config['base_url']}/{model}:generateContent?key={api_key}"

        async with httpx.AsyncClient(timeout=provider_config["timeout_seconds"]) as client:
            response = await asyncio.wait_for(
                client.post(url, json={"contents": contents}),
                timeout=provider_config["timeout_seconds"]
            )
            response.raise_for_status()
            data = response.json()

        # Extract text from Gemini response format
        text = data["candidates"][0]["content"]["parts"][0]["text"]

        logger.info(
            "llm_call_success",
            provider="gemini",
            model=model,
            latency_ms=0,
        )
        return text

    async def _call_openai_compatible_provider(self, provider_config: dict, model: str, messages: list, system_prompt: str, max_tokens_override: int = None) -> str:
        api_key = self._get_api_key(provider_config)
        if not api_key:
            raise ValueError(f"No API key configured for {provider_config['name']}")

        full_messages = [{"role": "system", "content": system_prompt}] + messages

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
                max_tokens=max_tokens_override or settings.LLM_MAX_TOKENS,
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

    async def _try_openrouter_models(self, provider_config: dict, model_list: list, messages: list, system_prompt: str, max_tokens_override: int = None) -> str:
        last_error = None
        for attempt_number, model in enumerate(model_list, start=1):
            try:
                logger.debug("openrouter_model_attempt", model=model, attempt=attempt_number)
                return await self._call_openai_compatible_provider(
                    provider_config=provider_config, model=model,
                    messages=messages, system_prompt=system_prompt,
                    max_tokens_override=max_tokens_override,
                )
            except Exception as error:
                last_error = error
                logger.warning("openrouter_model_failed", model=model, attempt=attempt_number, error=str(error))
        raise last_error

    async def complete(self, messages: list, system_prompt: str, complexity: QueryComplexity = QueryComplexity.COMPLEX, request_id: str = "unknown", max_tokens_override: int = None) -> dict:
        last_error = None
        providers_tried = []

        for provider_config in PROVIDER_CONFIGS:
            provider_name = provider_config["name"]

            if not self._get_api_key(provider_config):
                logger.debug("provider_skipped_no_key", provider=provider_name)
                continue

            if not await self._is_provider_healthy(provider_name):
                logger.debug("provider_skipped_unhealthy", provider=provider_name)
                continue

            providers_tried.append(provider_name)

            try:
                model_for_complexity = provider_config["models"][complexity]

                if provider_config.get("custom_handler") == "gemini":
                    model_list = model_for_complexity if isinstance(model_for_complexity, list) else [model_for_complexity]
                    response_text = None
                    model_used = "gemini_model"
                    for gemini_model in model_list:
                        try:
                            response_text = await self._call_gemini_provider(
                                provider_config=provider_config,
                                model=gemini_model,
                                messages=messages,
                                system_prompt=system_prompt,
                            )
                            model_used = gemini_model
                            break
                        except Exception as gemini_error:
                            logger.warning("gemini_model_failed", model=gemini_model, error=str(gemini_error))
                            continue
                    if response_text is None:
                        raise ValueError("All Gemini models failed")
                elif isinstance(model_for_complexity, list):
                    response_text = await self._try_openrouter_models(
                        provider_config=provider_config, model_list=model_for_complexity,
                        messages=messages, system_prompt=system_prompt,
                        max_tokens_override=max_tokens_override,
                    )
                    model_used = "openrouter_free_model"
                else:
                    response_text = await self._call_openai_compatible_provider(
                        provider_config=provider_config, model=model_for_complexity,
                        messages=messages, system_prompt=system_prompt,
                        max_tokens_override=max_tokens_override,
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
                logger.warning("provider_timeout", provider=provider_name, timeout=provider_config["timeout_seconds"])
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
                logger.warning("provider_error", provider=provider_name, error=str(error), error_type=type(error).__name__, request_id=request_id)
                await self._mark_provider_unhealthy(provider_name, ttl_seconds=unhealthy_ttl)

        logger.error("all_providers_failed", providers_tried=providers_tried, last_error=str(last_error))
        await self._send_critical_alert(
            f"ALL LLM PROVIDERS FAILED\nProviders tried: {providers_tried}\nLast error: {last_error}\nRequest ID: {request_id}"
        )

        from core.exceptions import AIServiceError
        raise AIServiceError("AI service is temporarily unavailable. Please try again in a moment.")

    async def _send_critical_alert(self, message: str) -> None:
        if not settings.RESEND_API_KEY:
            return
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "from": settings.ALERT_FROM_EMAIL,
                        "to": ["nwekechinelo25@yahoo.com"],
                        "subject": "🚨 Pillara — All AI Providers Down",
                        "html": f"<h2>🚨 PILLARA CRITICAL ALERT</h2><p>{message}</p>"
                    }
                )
        except Exception as error:
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
        if any(keyword in query_lower for keyword in complex_keywords):
            return QueryComplexity.COMPLEX
        if len(query.split()) > 15:
            return QueryComplexity.COMPLEX
        return QueryComplexity.SIMPLE