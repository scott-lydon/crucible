"""Test fixtures. The database is real (a throwaway ``crucible_test`` Postgres
database migrated with Alembic) — never mocked, per constitution.md section 8. The
schema is built by ``alembic upgrade head`` so tests exercise the same migrations
production runs."""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import asyncpg
import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parent.parent
TEST_DB = "crucible_test"
# Defaults target the local crucible-pg container; CI overrides via PGHOST/PGPORT.
PGHOST = os.environ.get("PGHOST", "127.0.0.1")
PGPORT = int(os.environ.get("PGPORT", "55432"))
PGUSER = os.environ.get("PGUSER", "crucible")
PGPASSWORD = os.environ.get("PGPASSWORD", "crucible")
_TABLES = "runs, specs, attacks, verdicts, llm_calls, sandbox_jobs, health_probes"


async def _admin_exec(database: str, sql: str) -> None:
    conn = await asyncpg.connect(
        host=PGHOST, port=PGPORT, user=PGUSER, password=PGPASSWORD, database=database
    )
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def _sql(database: str, sql: str) -> None:
    asyncio.run(_admin_exec(database, sql))


@pytest.fixture(scope="session", autouse=True)
def _migrated_test_db() -> Iterator[None]:
    _sql("postgres", f"DROP DATABASE IF EXISTS {TEST_DB}")
    _sql("postgres", f"CREATE DATABASE {TEST_DB}")
    os.environ["DATABASE_URL"] = (
        f"postgresql+asyncpg://{PGUSER}:{PGPASSWORD}@{PGHOST}:{PGPORT}/{TEST_DB}"
    )
    subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=REPO, env=dict(os.environ), check=True, capture_output=True, text=True,
    )
    yield


@pytest.fixture(scope="session", autouse=True)
def _fraud_model(_migrated_test_db: None) -> None:
    # Train fraud-v1 once per session if the (gitignored) artifact is missing, so the
    # container's fraud target loads. Idempotent and cheap when already trained.
    from modules.targets.fraud.train import ensure_model

    ensure_model(1)


@pytest.fixture(scope="session")
def client(_fraud_model: None) -> Iterator[TestClient]:
    # One TestClient (one event loop, one async engine) for the whole session, so the
    # asyncpg engine is never used across loops.
    from orchestrator.api import app
    from orchestrator.wiring import build_container, set_container

    set_container(build_container())
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clean_tables() -> None:
    _sql(TEST_DB, f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE")


FRAUD_SPEC_YAML = """
spec_id: fraud-demo-v1
target_kind: fraud
shape: shape1_ml
holdout_generator_kind: data_partition
obligations:
  - id: catch-fraud
    description: A transaction labelled fraudulent must score above the decision threshold.
    check_kind: label_match
    params: {threshold: 0.5}
invariants:
  - id: amount-nonneg
    description: Transaction amount is non-negative.
    expression: "amount >= 0"
"""

DUMMY_SPEC_YAML = """
spec_id: dummy-demo-v1
target_kind: dummy
shape: shape1_ml
holdout_generator_kind: data_partition
obligations:
  - id: catch-fraud
    description: A transaction labelled fraudulent must score above the decision threshold.
    check_kind: label_match
    params: {threshold: 0.5}
invariants:
  - id: amount-nonneg
    description: Transaction amount is non-negative.
    expression: "amount >= 0"
"""
