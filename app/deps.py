"""FastAPI dependencies. Kept thin — most logic lives in app.db and app.config."""

from __future__ import annotations

import redis

from app.config import Settings, get_settings


def get_settings_dep() -> Settings:
    """FastAPI dependency form of get_settings()."""
    return get_settings()


def get_redis_client(settings: Settings | None = None) -> redis.Redis:
    """Construct a Redis client from settings.

    Not a dependency-yielding generator — we don't want connection pooling
    inside a single request for a smoke-test health check. The Celery broker
    uses its own connection.
    """
    settings = settings or get_settings()
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)
