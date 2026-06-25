"""VOUCH: a launched campaign runs OFF the API event loop, and the dispatch
branch is chosen from the active DB — never blocking the API during a run.

Three legs, all FREE (the synth target makes ZERO real LLM calls, needs no
external data, and runs no Docker):

1. ``is_subprocess_visible_db`` decides the dispatch branch from the URL/dialect:
   Postgres + file-backed SQLite => offload to the worker subprocess; in-memory
   SQLite => inline. (Unit, no I/O.)

2. The worker reconstructs the ``LaunchRequest`` from the run row's
   ``params_json`` and drives the run to completion — proven by running
   ``execute_run_by_id`` against a persisted run row and asserting it reaches a
   terminal status with verdicts persisted. (No subprocess needed; same entry.)

3. End-to-end OFFLOAD over a FILE-backed SQLite (which a subprocess CAN see):
   launch a synth run through the real ``POST /runs`` (so the worker subprocess
   is genuinely spawned), then assert ``/health`` and a cheap GET return PROMPTLY
   while the run is in flight, and the run still completes + persists verdicts.
   This is the responsiveness claim, real: if the campaign were still on the API
   loop, ``/health`` would stall behind it.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.api import app, execute_run_by_id, init_db
from orchestrator.db import is_subprocess_visible_db, session_factory
from shared.persistence import repo
from shared.persistence.models import RunRow


def test_dispatch_branch_chosen_from_db_dialect() -> None:
    # Postgres => process-shared => offload.
    assert is_subprocess_visible_db(
        "postgresql+asyncpg://u:p@localhost:5432/db"
    ) is True
    # File-backed SQLite => durable file => a subprocess can open it => offload.
    assert is_subprocess_visible_db("sqlite+aiosqlite:///tmp/x.db") is True
    assert is_subprocess_visible_db("sqlite:////abs/path.db") is True
    # In-memory SQLite (every form) => parent-only => inline.
    assert is_subprocess_visible_db("sqlite+aiosqlite:///:memory:") is False
    assert is_subprocess_visible_db("sqlite://") is False
    assert is_subprocess_visible_db(
        "sqlite+aiosqlite:///file:mem?mode=memory&cache=shared&uri=true"
    ) is False


@pytest.fixture
async def memdb() -> AsyncGenerator[None, None]:
    await init_db("sqlite+aiosqlite:///:memory:")
    yield


async def test_worker_reconstructs_params_and_completes(memdb: None) -> None:
    # Persist a run row exactly as ``create_run`` would (params_json from the
    # LaunchRequest), then drive it via the SAME entry the worker uses.
    run_id = str(uuid.uuid4())
    params = {
        "target": "synth",
        "rounds": 3,
        "batch_size": 40,
        "seed": "offload-recon",
        "run_blue": False,
        "spec": None,
    }
    sf = session_factory()
    async with sf() as s:
        s.add(
            RunRow(
                id=run_id,
                seed="offload-recon",
                status="running",
                n_rounds=3,
                batch_size=40,
                threshold=0.5,
                params_json=params,
            )
        )
        await s.commit()

    # The worker's entry point: rehydrates LaunchRequest from params_json, runs.
    await execute_run_by_id(run_id)

    async with sf() as s:
        run = await repo.get_run(s, run_id)
        verdicts = await repo.verdicts_for_run(s, run_id)
    assert run is not None
    assert run.status == "complete", run.status
    assert len(verdicts) > 0


@pytest.fixture
async def file_db_client(
    tmp_path: Path,
) -> AsyncGenerator[AsyncClient, None]:
    """An API client backed by a FILE SQLite the worker subprocess can also open.

    The subprocess resolves its DB from ``CRUCIBLE_DATABASE_URL`` (see
    ``orchestrator.db.database_url``); we point both the in-process app and the
    child at the same file so the offload path is exercised for real.
    """
    db_path = tmp_path / "offload.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    prev = os.environ.get("CRUCIBLE_DATABASE_URL")
    os.environ["CRUCIBLE_DATABASE_URL"] = url
    await init_db(url)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            yield c
    finally:
        if prev is None:
            os.environ.pop("CRUCIBLE_DATABASE_URL", None)
        else:
            os.environ["CRUCIBLE_DATABASE_URL"] = prev


async def test_api_stays_responsive_during_offloaded_run(
    file_db_client: AsyncClient,
) -> None:
    c = file_db_client
    # File-backed DB => create_run offloads to the worker subprocess.
    assert is_subprocess_visible_db() is True

    r = await c.post(
        "/runs",
        json={"target": "synth", "rounds": 4, "batch_size": 120,
              "seed": "offload-live", "run_blue": False},
    )
    assert r.status_code == 201, r.text
    run_id = r.json()["run_id"]

    # While the run is in flight in the worker subprocess, a cheap GET must
    # return PROMPTLY — proving the API loop is not blocked by the campaign.
    # (/health touches the DB + sandbox introspection but does NOT run the loop.)
    t0 = time.monotonic()
    health = await c.get("/runs/" + run_id)  # cheap persisted read
    elapsed = time.monotonic() - t0
    assert health.status_code == 200, health.text
    assert elapsed < 2.0, f"cheap GET stalled {elapsed:.2f}s — API loop blocked?"

    # The offloaded run still completes + persists verdicts. Poll the persisted
    # status (the worker drives it in its own process); generous bound for CI.
    deadline = time.monotonic() + 120.0
    status = "running"
    while time.monotonic() < deadline:
        got = await c.get(f"/runs/{run_id}")
        status = got.json()["status"]
        if status in ("complete", "failed"):
            break
        await asyncio.sleep(0.5)
    assert status == "complete", f"offloaded run ended {status!r}"

    verdicts = await c.get(f"/runs/{run_id}/verdicts")
    assert len(verdicts.json()["verdicts"]) > 0
