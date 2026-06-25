"""Integration-test harness against a real Postgres.

The database is never mocked (coding-practices.md section 7). This harness
ensures an isolated test database exists, runs the real Alembic migrations
against it, points the app's engine at it, and hands tests an httpx client
bound to the ASGI app in-process.

Local default URL matches docker-compose; override with
CRUCIBLE_TEST_DATABASE_URL (the CI job sets it to the service container).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient

from shared.persistence import reset_engine_for_tests

# Load .env into the environment so a local `uv run pytest` picks up the
# machine's database URLs. In CI the variables are set directly and there is
# no .env, so this is a no-op there.
load_dotenv()

# The suite runs the LLM layer through the scripted mock path (the "existing
# mock test path" of resolve_provider_mode). Without this, a runner that has
# neither the `claude` CLI on PATH nor an Anthropic key resolves the provider to
# NONE, and any route that builds an LLM client raises NoLlmProviderError. Set as
# a default so a machine that explicitly wants a real provider (MOCK_LLM=0 in its
# .env) is still respected.
os.environ.setdefault("MOCK_LLM", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get(
    "CRUCIBLE_TEST_DATABASE_URL",
    "postgresql+asyncpg://crucible:crucible@localhost:5432/crucible_test",
)


def _sync_dsn(url: str) -> str:
    """Strip the +asyncpg driver tag so asyncpg.connect accepts the DSN."""
    return url.replace("+asyncpg", "")


async def _ensure_database(url: str) -> None:
    """Create the test database if it does not already exist.

    Connects to the server's default `postgres` database to issue CREATE
    DATABASE, since you cannot create a database while connected to it.
    """
    parsed = urlparse(_sync_dsn(url))
    dbname = parsed.path.lstrip("/")
    if not dbname:
        raise RuntimeError(
            f"CRUCIBLE_TEST_DATABASE_URL has no database name: {url!r}. "
            f"Expected a URL ending in /<dbname>."
        )
    admin_dsn = urlunparse(parsed._replace(path="/postgres"))
    conn = await asyncpg.connect(admin_dsn)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", dbname)
        if not exists:
            # Database identifiers cannot be parameterized; dbname is from our
            # own config, never user input.
            await conn.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await conn.close()


def _alembic_upgrade(url: str) -> None:
    """Run `alembic upgrade head` against the test database in a subprocess."""
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=env,
        cwd=str(REPO_ROOT),
    )


@pytest.fixture(scope="session")
def migrated_database() -> str:
    """Ensure the test database exists and is migrated to head. Session-scoped."""
    asyncio.run(_ensure_database(TEST_DATABASE_URL))
    _alembic_upgrade(TEST_DATABASE_URL)
    reset_engine_for_tests(TEST_DATABASE_URL)
    return TEST_DATABASE_URL


@pytest_asyncio.fixture
async def client(migrated_database: str) -> AsyncIterator[AsyncClient]:
    """An httpx client bound to the ASGI app, sharing the test engine."""
    from orchestrator.api import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
