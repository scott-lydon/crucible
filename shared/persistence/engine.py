from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncSession,
                                     async_sessionmaker, create_async_engine)
from sqlalchemy.orm import Session, sessionmaker
from shared.persistence.models import Base

def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, future=True)

def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)

async def create_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# --- Sync write path (loop-safe llm_calls persistence) ----------------------
# Async asyncpg connections are pinned to the loop that created them, so they
# cannot be reused from a foreign loop/thread. ``PersistingLLMProvider`` runs
# inside the orchestrator's running loop via a SYNCHRONOUS ``complete()`` and
# must record one row without touching the async engine. The robust fix is a
# separate, dialect-neutral SYNC engine built from the SAME DB URL — no event
# loop is involved on the write path, so no cross-loop hazard exists.

# Async-driver -> sync-driver substitutions. Each async SQLAlchemy URL has a
# sync counterpart that talks to the same database with a blocking driver.
_SYNC_DRIVER_MAP = {
    "postgresql+asyncpg": "postgresql+psycopg",
    "sqlite+aiosqlite": "sqlite",
}


def sync_url(async_url: str) -> str:
    """Translate an async SQLAlchemy URL to its sync-driver equivalent.

    ``postgresql+asyncpg://...`` -> ``postgresql+psycopg://...`` (psycopg3, a sync
    blocking driver); ``sqlite+aiosqlite://...`` -> ``sqlite://...`` (stdlib). A URL
    that is already sync (no known async driver prefix) is returned unchanged, so
    callers can pass either form.
    """
    for async_driver, sync_driver in _SYNC_DRIVER_MAP.items():
        if async_url.startswith(async_driver):
            return sync_driver + async_url[len(async_driver):]
    return async_url


def make_sync_engine(url: str) -> Engine:
    """A blocking SQLAlchemy engine for the loop-safe sync write path.

    ``url`` may be the async URL — it is translated via ``sync_url`` first — so
    callers can hand in the same ``CRUCIBLE_DATABASE_URL`` the async engine uses.
    """
    return create_engine(sync_url(url), future=True)


def make_sync_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
