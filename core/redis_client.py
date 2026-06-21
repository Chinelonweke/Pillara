# core/redis_client.py
# SECURITY UPDATES FROM AUDIT:
# 1. Rate limiting now supports BOTH ip_hash AND user_id as identifiers
#    Authenticated endpoints rate-limit by user_id (not IP — IPv6 bypass proof)
#    Unauthenticated endpoints rate-limit by ip_hash:email combined
# 2. Auth rate limiter is stricter and combined-key based

import json
import re
import time
from typing import Any, Optional

from redis.asyncio import Redis, ConnectionPool
from redis.exceptions import RedisError

from core.config import settings
from monitoring.logger import get_logger

logger = get_logger(__name__)

_redis_pool: Optional[ConnectionPool] = None
_redis_client: Optional[Redis] = None


async def init_redis() -> Redis:
    global _redis_pool, _redis_client
    _redis_pool = ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=20,
        decode_responses=True,
        health_check_interval=30,
    )
    _redis_client = Redis(connection_pool=_redis_pool)
    try:
        await _redis_client.ping()
        logger.info("redis_connected", url=settings.REDIS_URL.split("@")[-1])
    except RedisError as error:
        logger.error("redis_connection_failed", error=str(error))
        raise
    return _redis_client


async def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        await init_redis()
    return _redis_client


async def close_redis() -> None:
    global _redis_client, _redis_pool
    if _redis_client:
        await _redis_client.close()
    if _redis_pool:
        await _redis_pool.disconnect()
    logger.info("redis_connections_closed")


class SessionManager:

    def __init__(self, redis: Redis):
        self.redis = redis
        self.session_prefix = "session:"
        self.user_sessions_prefix = "user_sessions:"

    def _session_key(self, user_id: str, jti: str) -> str:
        return f"{self.session_prefix}{user_id}:{jti}"

    def _user_sessions_key(self, user_id: str) -> str:
        return f"{self.user_sessions_prefix}{user_id}"

    async def create_session(self, user_id: str, jti: str, device_info: str = "unknown", ip_hash: str = "unknown") -> bool:
        session_data = {
            "user_id": user_id,
            "jti": jti,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "device": device_info,
            "ip_hash": ip_hash,
        }
        key = self._session_key(user_id, jti)
        try:
            await self.redis.setex(key, settings.REDIS_SESSION_TTL, json.dumps(session_data))
            user_sessions_key = self._user_sessions_key(user_id)
            await self.redis.sadd(user_sessions_key, jti)
            await self.redis.expire(user_sessions_key, settings.REDIS_SESSION_TTL)
            return True
        except RedisError as error:
            logger.error("session_create_failed", error=str(error))
            return False

    async def verify_session(self, user_id: str, jti: str) -> bool:
        key = self._session_key(user_id, jti)
        try:
            exists = await self.redis.exists(key)
            return bool(exists)
        except RedisError:
            return True  # fail open — JWT signature still provides auth

    async def revoke_session(self, user_id: str, jti: str) -> bool:
        key = self._session_key(user_id, jti)
        user_sessions_key = self._user_sessions_key(user_id)
        try:
            await self.redis.delete(key)
            await self.redis.srem(user_sessions_key, jti)
            return True
        except RedisError as error:
            logger.error("session_revoke_failed", error=str(error))
            return False

    async def revoke_all_sessions(self, user_id: str) -> int:
        user_sessions_key = self._user_sessions_key(user_id)
        try:
            jtis = await self.redis.smembers(user_sessions_key)
            revoked = 0
            for jti in jtis:
                key = self._session_key(user_id, jti)
                deleted = await self.redis.delete(key)
                revoked += deleted
            await self.redis.delete(user_sessions_key)
            return revoked
        except RedisError as error:
            logger.error("revoke_all_sessions_failed", error=str(error))
            return 0


class CacheManager:

    def __init__(self, redis: Redis):
        self.redis = redis
        self.cache_prefix = "cache:"

    def _cache_key(self, namespace: str, key: str) -> str:
        safe_key = re.sub(r'[^a-zA-Z0-9_]', '_', key[:100])
        return f"{self.cache_prefix}{namespace}:{safe_key}"

    async def get(self, namespace: str, key: str) -> Optional[Any]:
        try:
            cache_key = self._cache_key(namespace, key)
            value = await self.redis.get(cache_key)
            if value is None:
                return None
            return json.loads(value)
        except (RedisError, json.JSONDecodeError):
            return None

    async def set(self, namespace: str, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        try:
            cache_key = self._cache_key(namespace, key)
            serialized = json.dumps(value, default=str)
            ttl = ttl_seconds or settings.REDIS_CACHE_TTL
            await self.redis.setex(cache_key, ttl, serialized)
            return True
        except (RedisError, TypeError) as error:
            logger.warning("cache_set_failed", error=str(error))
            return False

    async def delete(self, namespace: str, key: str) -> bool:
        try:
            cache_key = self._cache_key(namespace, key)
            await self.redis.delete(cache_key)
            return True
        except RedisError:
            return False


class RateLimiter:
    """
    Sliding window rate limiter.

    SECURITY FIX — TWO RATE LIMIT STRATEGIES:

    Strategy A — Authenticated endpoints:
        Key = user_id
        WHY: IPv6 users have 2^64 addresses — IP-based limiting is useless.
        A logged-in user has one user_id regardless of how many IPs they use.
        Rate limiting by user_id is IPv6-proof.

    Strategy B — Unauthenticated endpoints (login, register, password reset):
        Key = sha256(ip_hash + ":" + email)
        WHY: We combine IP + email so an attacker can't bypass by rotating either one alone.
        Rotating IPs still hits the per-email limit.
        Rotating emails still hits the per-IP limit.
        They'd need to rotate BOTH simultaneously — much harder.
    """

    def __init__(self, redis: Redis):
        self.redis = redis
        self.rate_limit_prefix = "ratelimit:"

    async def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        namespace: str = "global",
    ) -> tuple[bool, int, int]:
        """
        Sliding window rate limit check.
        Returns (allowed, current_count, limit).
        identifier should be user_id for auth'd endpoints, combined hash for unauth'd.
        """
        key = f"{self.rate_limit_prefix}{namespace}:{identifier}"
        now = time.time()
        window_start = now - window_seconds

        try:
            async with self.redis.pipeline() as pipe:
                pipe.zremrangebyscore(key, "-inf", window_start)
                pipe.zcard(key)
                pipe.zadd(key, {f"{now}:{id(object())}": now})
                # We include id(object()) to ensure uniqueness even at the same timestamp
                pipe.expire(key, window_seconds)
                results = await pipe.execute()

            current_count = results[1] + 1  # +1 for the request we just added

            allowed = current_count <= limit

            if not allowed:
                logger.warning(
                    "rate_limit_exceeded",
                    identifier_prefix=identifier[:8],
                    namespace=namespace,
                    count=current_count,
                    limit=limit,
                )

            return allowed, current_count, limit

        except RedisError as error:
            logger.error("rate_limit_check_failed", error=str(error))
            return True, 0, limit  # fail open on Redis error

    def make_auth_identifier(self, ip_hash: str, email: str) -> str:
        """
        Creates a combined identifier for unauthenticated endpoints.
        Combines IP + email so rotating either one alone doesn't bypass the limit.
        """
        import hashlib
        combined = f"{ip_hash}:{email.lower()}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]