import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.persistence import make_engine, make_session_factory, create_all

_session_factory: async_sessionmaker[AsyncSession] | None = None

# Runtime/prod default: the local Postgres 16 container from compose.yaml.
# Tests pass an explicit ``sqlite+aiosqlite://`` URL, so they never touch this.
DEFAULT_DATABASE_URL = "postgresql+asyncpg://crucible:crucible@localhost:5432/crucible_dev"


def database_url() -> str:
    """The runtime DB URL: ``CRUCIBLE_DATABASE_URL`` env, or the local Postgres."""
    return os.environ.get("CRUCIBLE_DATABASE_URL", DEFAULT_DATABASE_URL)


async def init_db(url: str | None = None) -> None:
    """Create the schema and build the session factory.

    ``url=None`` resolves from env (``CRUCIBLE_DATABASE_URL``) and defaults to the
    local Postgres container. Tests pass an explicit SQLite URL to stay fast and
    Postgres-free.

    Schema posture: PROD/Postgres is migrated with Alembic (``alembic upgrade
    head``; baseline in ``alembic/versions/``); TESTS keep this fast
    ``create_all`` path on in-memory SQLite and never require Alembic/Postgres.
    Low-risk choice: ``create_all`` stays the app default (idempotent — it skips
    existing tables), Alembic is the migration tool run out-of-band, not wired
    into startup.
    """
    global _session_factory
    engine = make_engine(url if url is not None else database_url())
    await create_all(engine)
    _session_factory = make_session_factory(engine)


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("init_db must be called before session_factory")
    return _session_factory
