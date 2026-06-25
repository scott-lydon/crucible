"""VOUCH for stop-run (cooperative cancellation).

All FREE (synth target: ZERO real LLM calls, no external data, no Docker),
inline against in-memory SQLite:

1. A run flagged for cancellation exits and ends ``stopped`` — the cooperative
   path. We set ``cancel_requested`` on a persisted run, drive it via the SAME
   entry the worker uses (``execute_run_by_id``), and assert the loop stopped at
   the terminal ``stopped`` status (the between-rounds check fired before any
   round, so no rounds were persisted — a clean graceful exit).

2. ``POST /runs/{id}/stop`` returns the new status, is idempotent on an
   already-terminal run (the terminal status is preserved, not overwritten), and
   404s an unknown run.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.api import app, execute_run_by_id, init_db
from orchestrator.db import session_factory
from shared.persistence import repo
from shared.persistence.models import RoundRow, RunRow
from sqlalchemy import select


def _synth_run_row(run_id: str, *, cancel: bool) -> RunRow:
    return RunRow(
        id=run_id,
        seed="stop-test",
        status="running",
        n_rounds=3,
        batch_size=40,
        threshold=0.5,
        params_json={
            "target": "synth",
            "rounds": 3,
            "batch_size": 40,
            "seed": "stop-test",
            "run_blue": False,
            "spec": None,
        },
        cancel_requested=cancel,
    )


@pytest.fixture
async def memdb() -> AsyncGenerator[None, None]:
    await init_db("sqlite+aiosqlite:///:memory:")
    yield


async def test_cancel_requested_run_exits_stopped(memdb: None) -> None:
    run_id = str(uuid.uuid4())
    sf = session_factory()
    # Persist a run already flagged for cancellation, then drive it.
    async with sf() as s:
        s.add(_synth_run_row(run_id, cancel=True))
        await s.commit()

    await execute_run_by_id(run_id)

    async with sf() as s:
        run = await repo.get_run(s, run_id)
        rounds = (
            await s.execute(select(RoundRow).where(RoundRow.run_id == run_id))
        ).scalars().all()
    assert run is not None
    assert run.status == "stopped", run.status
    # The cancel was honored BEFORE round 0's work — a clean graceful exit.
    assert len(rounds) == 0


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    await init_db("sqlite+aiosqlite:///:memory:")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def test_stop_endpoint_sets_stopping_then_idempotent(client: AsyncClient) -> None:
    run_id = str(uuid.uuid4())
    async with session_factory()() as s:
        s.add(_synth_run_row(run_id, cancel=False))
        await s.commit()

    # First stop: a running run moves to the transient ``stopping`` status.
    r1 = await client.post(f"/runs/{run_id}/stop")
    assert r1.status_code == 200, r1.text
    assert r1.json() == {"run_id": run_id, "status": "stopping"}

    # Simulate the loop reaching the terminal ``stopped`` status.
    async with session_factory()() as s:
        run = await repo.get_run(s, run_id)
        assert run is not None
        run.status = "stopped"
        await s.commit()

    # Idempotent: stopping an already-terminal run preserves its terminal status.
    r2 = await client.post(f"/runs/{run_id}/stop")
    assert r2.status_code == 200, r2.text
    assert r2.json() == {"run_id": run_id, "status": "stopped"}


async def test_stop_unknown_run_404(client: AsyncClient) -> None:
    r = await client.post(f"/runs/{uuid.uuid4()}/stop")
    assert r.status_code == 404, r.text
