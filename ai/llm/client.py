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
        # The key in settings to get the API key
        # We use the setting name (string) not the value directly
        # because this config is defined at module load time,
        # before the API key is needed

        # Models for this provider
        # We use two models: 70B for complex, 8B for simple queries
        "models": {
            QueryComplexity.COMPLEX: "llama-3.3-70b-versatile",
            QueryComplexity.SIMPLE:  "llama-3.1-8b-instant",
        },
        "timeout_seconds": 8,
        # Fail fast — 8 seconds max. If Groq is slow, move to Cerebras.

        "extra_headers": {},
        # Some providers need extra headers (OpenRouter does — see below)
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
        # OpenRouter has 4 free models — we try them in order within this provider
        # The first model in the list is tried first
        # :free suffix = OpenRouter free tier models
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
        # OpenRouter adds routing overhead — give it more time
        "extra_headers": {
            # Required by OpenRouter's terms — identifies your app
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
        # Last resort — give it the most time. Slow but reliable.
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
        """
        redis: optional Redis client for provider health caching.
        If not provided, health caching is skipped (still works, just slower on failures).
        """
        self.redis = redis

        # Key prefix for provider health in Redis
        # "llm_health:groq" stores whether Groq is currently healthy
        self._health_key_prefix = "llm_health:"

    def _get_api_key(self, provider_config: dict) -> Optional[str]:
        """
        Gets the API key for a provider from settings.

        WHY USE getattr:
        getattr(settings, "GROQ_API_KEY") reads the attribute named "GROQ_API_KEY"
        from the settings object dynamically.
        This lets us store the attribute NAME in our config dict
        and look up the actual value at runtime.

        WHY NOT HARDCODE THE KEY IN THE CONFIG:
        The config is defined at module load time.
        At that point, settings might not have the key yet (AWS secrets loading).
        We look up the key when we need it — lazy evaluation.
        """
        key_setting_name = provider_config["api_key_setting"]
        # getattr(object, name, default) — returns default if attribute not found
        api_key = getattr(settings, key_setting_name, None)
        return api_key

    async def _is_provider_healthy(self, provider_name: str) -> bool:
        """
        Checks if a provider is currently healthy (not rate limited / erroring).

        Returns True if healthy (try this provider), False if unhealthy (skip it).

        WHY CHECK REDIS:
        We cache provider health for 60 seconds.
        If Groq was rate limited 10 seconds ago, it's probably still rate limited.
        Skipping it saves 8 seconds of timeout per request.
        """
        if not self.redis:
            return True  # no Redis = can't check = assume healthy

        try:
            key = f"{self._health_key_prefix}{provider_name}"
            # redis.get() returns None if key doesn't exist (healthy)
            # returns "unhealthy" if we marked it as such
            status = await self.redis.get(key)
            return status is None  # None = key not set = healthy
        except Exception:
            return True  # if Redis fails, assume provider is healthy

    async def _mark_provider_unhealthy(
        self,
        provider_name: str,
        ttl_seconds: int = None
    ) -> None:
        """
        Marks a provider as unhealthy in Redis for ttl_seconds.
        After ttl_seconds, the key expires and the provider is tried again.

        WHY TTL (not permanent):
        Rate limits reset. Temporary outages resolve.
        We don't want to permanently exclude a provider after one bad moment.
        60 seconds is enough to let rate limits reset in most cases.
        """
        if not self.redis:
            return

        ttl = ttl_seconds or settings.LLM_PROVIDER_HEALTH_CACHE_TTL

        try:
            key = f"{self._health_key_prefix}{provider_name}"
            # setex = SET with EXpiry
            await self.redis.setex(key, ttl, "unhealthy")
        except Exception:
            pass  # health cache failure is non-fatal

    async def _call_openai_compatible_provider(
        self,
        provider_config: dict,
        model: str,
        messages: list,
        system_prompt: str,
    ) -> str:
        """
        Makes an API call to any OpenAI-compatible provider.

        WHY ONE FUNCTION FOR MULTIPLE PROVIDERS:
        Groq, Cerebras, Together AI, and OpenRouter all implement
        the same OpenAI API spec. Same endpoint format, same request body,
        same response format. One function handles all four.
        Only the base_url and api_key change.

        Returns the response text as a string.
        Raises an exception if the call fails (caller handles it).
        """
        api_key = self._get_api_key(provider_config)
        if not api_key:
            raise ValueError(f"No API key configured for {provider_config['name']}")

        # Build the messages list
        # messages is a list of dicts: [{"role": "user", "content": "..."}]
        # We prepend the system prompt as the first message
        full_messages = [
            {"role": "system", "content": system_prompt}
        ] + messages
        # + on lists = concatenation (combine two lists into one)

        # Create an AsyncOpenAI client pointed at this provider's base URL
        # WHY CREATE PER CALL (not shared):
        # Each provider has a different base_url and api_key.
        # AsyncOpenAI client is lightweight to create — no connection overhead.
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=provider_config["base_url"],
            default_headers=provider_config.get("extra_headers", {}),
            timeout=provider_config["timeout_seconds"],
        )

        start_time = time.monotonic()

        # asyncio.wait_for adds a timeout wrapper around the API call
        # If the call takes longer than timeout_seconds, it raises asyncio.TimeoutError
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

        # Extract the text content from the response
        # response.choices is a list — [0] = first (and only) choice
        # .message.content = the actual text response
        response_text = response.choices[0].message.content

        logger.info(
            "llm_call_success",
            provider=provider_config["name"],
            model=model,
            latency_ms=round(latency_ms, 2),
            # WHY LOG THESE METRICS:
            # Latency tells you which provider is fastest in practice.
            # Token usage tells you your costs.
            # Tracking this lets you optimise provider selection over time.
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
        """
        Tries OpenRouter's free models in order until one succeeds.

        WHY SPECIAL HANDLING FOR OPENROUTER:
        OpenRouter has a LIST of free models (not just one model per complexity tier).
        We try them in order — if the first free model is rate limited,
        try the second, then third, then fourth.
        This gives OpenRouter 4 chances before we move to Together AI.

        Returns the response text from whichever model succeeded.
        Raises the last exception if all models fail.
        """
        last_error = None

        # Iterate through the list of models for this provider
        # enumerate gives us (index, model_name) pairs
        # We use index to log which attempt this is (attempt 1 of 4, etc.)
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
                return result  # success — stop trying other models

            except Exception as error:
                last_error = error
                logger.warning(
                    "openrouter_model_failed",
                    model=model,
                    attempt=attempt_number,
                    error=str(error),
                    error_type=type(error).__name__,
                )
                # continue to next model in the list

        # All OpenRouter models failed — raise the last error
        # so the outer fallback chain moves to Together AI
        raise last_error

    async def complete(
        self,
        messages: list,
        system_prompt: str,
        complexity: QueryComplexity = QueryComplexity.COMPLEX,
        request_id: str = "unknown",
    ) -> dict:
        """
        Main method — gets a completion from the best available provider.

        WHY RETURN A DICT (not just the response string):
        The caller often needs to know:
        - Which provider was used (for logging, monitoring)
        - Which model was used
        - Whether a fallback was triggered
        This context is useful for analytics and debugging.

        FALLBACK CHAIN LOGIC:
        We iterate through PROVIDER_CONFIGS in order.
        For each provider:
          1. Check if it has an API key configured (skip if not)
          2. Check if it's currently healthy in Redis (skip if rate limited)
          3. Try to make the API call
          4. If success: return the result
          5. If failure: mark as unhealthy, try next provider

        If ALL providers fail: raise AIServiceError.
        """
        last_error = None
        providers_tried = []  # track which providers we attempted

        # Loop through providers in priority order
        # This is the core of the fallback chain
        for provider_config in PROVIDER_CONFIGS:
            provider_name = provider_config["name"]

            # Step 1: Check if API key is configured
            api_key = self._get_api_key(provider_config)
            if not api_key:
                logger.debug(
                    "provider_skipped_no_key",
                    provider=provider_name
                )
                continue  # skip this provider, try next

            # Step 2: Check provider health cache
            is_healthy = await self._is_provider_healthy(provider_name)
            if not is_healthy:
                logger.debug(
                    "provider_skipped_unhealthy",
                    provider=provider_name
                )
                continue  # skip unhealthy provider, try next

            providers_tried.append(provider_name)

            try:
                # Step 3: Get the model for this provider and complexity level
                provider_models = provider_config["models"]
                model_for_complexity = provider_models[complexity]

                # Step 4: Make the API call
                # OpenRouter has a list of models; others have a single model string
                if isinstance(model_for_complexity, list):
                    # OpenRouter: try each free model in order
                    response_text = await self._try_openrouter_models(
                        provider_config=provider_config,
                        model_list=model_for_complexity,
                        messages=messages,
                        system_prompt=system_prompt,
                    )
                    model_used = "openrouter_free_model"
                else:
                    # All other providers: single model
                    response_text = await self._call_openai_compatible_provider(
                        provider_config=provider_config,
                        model=model_for_complexity,
                        messages=messages,
                        system_prompt=system_prompt,
                    )
                    model_used = model_for_complexity

                # Step 5: Success — return result with metadata
                return {
                    "text": response_text,
                    "provider": provider_name,
                    "model": model_used,
                    "complexity": complexity.value,
                    "fallback_triggered": provider_name != "groq",
                    # fallback_triggered = True if we didn't use the primary provider
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
                # Mark as unhealthy for a shorter time (timeout might be temporary)
                await self._mark_provider_unhealthy(provider_name, ttl_seconds=30)

            except Exception as error:
                last_error = error
                error_str = str(error).lower()

                # Determine appropriate unhealthy TTL based on error type
                # Rate limits reset after ~1 minute → 60 second TTL
                # Other errors might be transient → 30 second TTL
                if "rate" in error_str or "429" in error_str:
                    unhealthy_ttl = 60   # rate limited — wait a full minute
                elif "auth" in error_str or "401" in error_str:
                    unhealthy_ttl = 300  # auth error — wait 5 minutes (likely config issue)
                else:
                    unhealthy_ttl = 30   # other error — wait 30 seconds

                logger.warning(
                    "provider_error",
                    provider=provider_name,
                    error=str(error),
                    error_type=type(error).__name__,
                    unhealthy_ttl=unhealthy_ttl,
                    request_id=request_id,
                )
                await self._mark_provider_unhealthy(provider_name, ttl_seconds=unhealthy_ttl)

        # All providers failed — this is a critical situation
        logger.error(
            "all_providers_failed",
            providers_tried=providers_tried,
            last_error=str(last_error),
            request_id=request_id,
        )

        # Send Telegram alert if configured
        # This is the "wake up, something is very wrong" notification
        await self._send_critical_alert(
            f"ALL LLM PROVIDERS FAILED\n"
            f"Providers tried: {providers_tried}\n"
            f"Last error: {last_error}\n"
            f"Request ID: {request_id}"
        )

        # Import here to avoid circular imports
        from core.exceptions import AIServiceError
        raise AIServiceError(
            "AI service is temporarily unavailable. Please try again in a moment."
        )

    async def _send_critical_alert(self, message: str) -> None:
        """
        Sends a Telegram message to YOU when all providers fail.

        WHY TELEGRAM (not email):
        Telegram notifications are instant — they appear on your phone
        like a text message, even at 3am.
        Email might not be checked for hours.
        When all your AI providers are down, you want to know NOW.

        WHY ASYNC:
        We don't want the failed request to wait for the Telegram API.
        We fire the alert and continue (even if Telegram fails).
        """
        if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
            return  # Telegram not configured — skip silently

        try:
            url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json={
                    "chat_id": settings.TELEGRAM_CHAT_ID,
                    "text": f"🚨 PILLARA ALERT\n\n{message}",
                    "parse_mode": "HTML"
                })
        except Exception as error:
            # If Telegram fails, log it but don't raise
            # We're already in an error state — adding another error helps no one
            logger.error("telegram_alert_failed", error=str(error))

    async def classify_query_complexity(self, query: str) -> QueryComplexity:
        """
        Determines whether a query needs a large (70B) or small (8B) model.

        WHY THIS MATTERS:
        8B model = faster, cheaper, good for simple questions
        70B model = slower, more capable, required for drug safety reasoning

        We use heuristics (rules) rather than another AI call to classify —
        calling an AI to decide which AI to use would be wasteful.

        HEURISTICS USED:
        - Query length (longer = likely more complex)
        - Presence of multiple drug names (interaction check = complex)
        - Safety-related keywords (complex)
        - Simple greeting or factual question (simple)

        Returns QueryComplexity enum value.
        """
        query_lower = query.lower()
        # .lower() normalises case — "Warfarin" and "warfarin" both match

        # Keywords that indicate a COMPLEX query requiring the 70B model
        # A set is used because we only need membership check (is keyword IN set?)
        # Sets have O(1) lookup vs O(n) for lists
        complex_keywords: set = {
            "interact", "interaction", "safe to take", "together",
            "combine", "combination", "side effect", "overdose",
            "dangerous", "risk", "harm", "safe", "avoid",
            "warning", "contraindicated", "allergy", "reaction",
            "dose", "dosage", "how much", "maximum", "minimum"
        }

        # Check if ANY complex keyword appears in the query
        # any() returns True if at least one item is True in the iterable
        # Here the iterable is a generator: (keyword in query_lower for keyword in complex_keywords)
        has_complex_keyword = any(
            keyword in query_lower
            for keyword in complex_keywords
        )

        if has_complex_keyword:
            return QueryComplexity.COMPLEX

        # Long queries are usually more complex
        word_count = len(query.split())
        # str.split() splits by whitespace, returns a list of words
        # len() counts the items in the list
        if word_count > 15:
            return QueryComplexity.COMPLEX

        # Default to SIMPLE for short, keyword-free queries
        return QueryComplexity.SIMPLE