import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.persistence import make_engine, make_session_factory, create_all

_session_factory: async_sessionmaker[AsyncSession] | None = None
_active_url: str | None = None

# Runtime/prod default: the local Postgres 16 container from compose.yaml.
# Tests pass an explicit ``sqlite+aiosqlite://`` URL, so they never touch this.
DEFAULT_DATABASE_URL = "postgresql+asyncpg://crucible:crucible@localhost:5432/crucible_dev"


def database_url() -> str:
    """The runtime DB URL: ``CRUCIBLE_DATABASE_URL`` env, or the local Postgres."""
    return os.environ.get("CRUCIBLE_DATABASE_URL", DEFAULT_DATABASE_URL)


def active_database_url() -> str:
    """The URL ``init_db`` actually initialized the engine with.

    The loop-safe sync ``llm_calls`` writer must target the SAME database the app
    is running on — Postgres in prod, the test's explicit SQLite URL under test —
    not whatever ``database_url()`` resolves from env. Tests pass an explicit URL
    to ``init_db``; using THAT keeps the writer pointed at the live DB.
    """
    if _active_url is None:
        raise RuntimeError("init_db must be called before active_database_url")
    return _active_url


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
    global _session_factory, _active_url
    resolved = url if url is not None else database_url()
    engine = make_engine(resolved)
    await create_all(engine)
    _session_factory = make_session_factory(engine)
    _active_url = resolved


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("init_db must be called before session_factory")
    return _session_factory


def is_subprocess_visible_db(url: str | None = None) -> bool:
    """Whether the active DB can be opened by a *separate* worker process.

    A worker subprocess opens its OWN engine from the same URL, so it can only
    reach the run's rows if the database is durable/shared across processes:
    Postgres (a network server) and a FILE-backed SQLite both qualify. An
    in-memory SQLite (``:memory:`` or a bare ``sqlite://``) lives only in the
    parent process's address space, so a subprocess would see an EMPTY DB — for
    that case the run must execute INLINE in the API process instead.

    This is the dispatch switch for ``create_run``: subprocess-visible => offload
    the campaign to ``orchestrator.worker`` (API loop never blocks); in-memory
    SQLite (the test suite) => keep the current inline ``BackgroundTasks`` path.
    Decided from the active DB URL/dialect, never a brittle env guess.
    """
    resolved = url if url is not None else active_database_url()
    if not resolved.startswith("sqlite"):
        # Postgres (or any networked server dialect) is process-shared.
        return True
    # SQLite: file-backed is shareable; in-memory (":memory:" / bare "sqlite://"
    # / "mode=memory") is not. Normalize the path portion after the scheme.
    after_scheme = resolved.split("://", 1)[1] if "://" in resolved else resolved
    path = after_scheme.split("?", 1)[0]
    is_in_memory = path in ("", "/:memory:", ":memory:") or "mode=memory" in resolved
    return not is_in_memory
