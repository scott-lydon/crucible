"""Async SQLAlchemy engine and session factory.

The engine and sessionmaker are module-level singletons (the one sanctioned
mutable-state exception in this file): they are expensive to build and must
be shared across the whole process. `get_session` is the FastAPI dependency
that yields one scoped session per request.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import NullPool, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import get_settings


def _normalize_async_url(url: str) -> str:
    """Map a plain `postgresql://` URL (Render, Supabase) to the asyncpg driver.

    Hosts hand out `postgresql://...`; SQLAlchemy async needs the explicit
    `+asyncpg` driver tag. Normalizing here means the rest of the code, and the
    .env file, can use whichever form the host gave us.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def async_database_url() -> str:
    """The configured database URL, normalized to the asyncpg driver.

    Single point of truth for both the app engine and the Alembic env, so the
    two can never point at differently-spelled URLs.
    """
    return _normalize_async_url(get_settings().database_url)


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, building it on first use."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _normalize_async_url(get_settings().database_url),
            echo=False,
            pool_pre_ping=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async session factory."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield one async session per request, closing it on exit."""
    async with get_sessionmaker()() as session:
        yield session


async def ping(session: AsyncSession) -> None:
    """Raise if the database is unreachable. Keeps the raw SELECT 1 inside the
    persistence layer (coding-practices.md: no raw SQL outside shared/persistence)."""
    await session.execute(text("SELECT 1"))


def use_database(url: str, *, connect_args: dict[str, Any] | None = None) -> None:
    """Point the process-wide engine and sessionmaker at `url`.

    The sanctioned hook for code outside a FastAPI request to drive the same
    engine the app uses: the integration suite aims it at the ephemeral test
    database, and the e2e real-LLM script aims it at the external production
    Postgres (passing ``connect_args={"ssl": "require"}`` for the TLS the
    managed host demands). Uses NullPool so no connection is pooled across
    pytest-asyncio's per-test event loops (a pooled asyncpg connection reused on
    a later loop raises "Event loop is closed" at teardown).
    """
    global _engine, _sessionmaker
    _engine = create_async_engine(
        _normalize_async_url(url),
        echo=False,
        poolclass=NullPool,
        connect_args=connect_args or {},
    )
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)


def reset_engine_for_tests(url: str) -> None:
    """Backwards-compatible alias used by the integration harness."""
    use_database(url)
