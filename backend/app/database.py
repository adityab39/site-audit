"""Database and cache connection setup.

SQLite vs PostgreSQL
--------------------
The engine is configured automatically based on the DATABASE_URL prefix:
  • sqlite+aiosqlite:///  – local dev, no extra services required
  • postgresql+asyncpg:// – production / Docker

Redis (optional)
----------------
When REDIS_ENABLED=false, or when Redis is simply unreachable, all cache
operations silently no-op via _NoopRedis. The application works normally —
audits just aren't cached between restarts.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# SQLAlchemy engine — dialect-aware configuration
# ---------------------------------------------------------------------------

def _make_engine():
    url = settings.database_url
    if url.startswith("sqlite"):
        # SQLite does not support connection-pool tuning parameters.
        # check_same_thread=False is required for async usage.
        return create_async_engine(
            url,
            echo=settings.debug,
            connect_args={"check_same_thread": False},
        )
    # PostgreSQL (asyncpg) — full pool configuration
    return create_async_engine(
        url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


engine = _make_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Redis — with silent no-op fallback
# ---------------------------------------------------------------------------

class _NoopRedis:
    """Drop-in Redis replacement used when Redis is disabled or unreachable.

    All cache reads return None (miss) and all writes are silently discarded.
    The application behaves correctly — just without caching.
    """

    async def get(self, key: str) -> None:
        return None

    async def setex(self, name: str, time: int, value: str) -> None:
        pass

    async def delete(self, *keys: str) -> int:
        return 0

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        pass


_redis_client: aioredis.Redis | _NoopRedis | None = None


async def get_redis() -> aioredis.Redis | _NoopRedis:
    """Return the shared Redis client, or a no-op stand-in if unavailable.

    Checks REDIS_ENABLED before making any network connection attempt,
    so startup never blocks or crashes when Redis is not installed.
    """
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    # Check the flag FIRST — no connection attempt at all when disabled
    if not settings.redis_enabled:
        logger.info("Redis disabled (REDIS_ENABLED=false) — caching skipped.")
        _redis_client = _NoopRedis()
        return _redis_client

    try:
        client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,  # fail fast; don't block startup
        )
        await client.ping()
        _redis_client = client
        logger.info("Redis connected at %s", settings.redis_url)
    except Exception as exc:
        logger.warning(
            "Redis unavailable (%s) — running without cache. "
            "Set REDIS_ENABLED=false to silence this warning.",
            exc,
        )
        _redis_client = _NoopRedis()

    return _redis_client


async def close_redis() -> None:
    """Close the Redis connection on application shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
