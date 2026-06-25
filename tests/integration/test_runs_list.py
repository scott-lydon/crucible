"""VOUCH for ``GET /runs``: the run picker the launcher reads (US-2).

Seeds ``RunRow``s directly against in-memory SQLite (ZERO real LLM calls, no
external data, no Docker) and asserts the exact contract: shape, newest-first
ordering by ``created_at``, the ``limit`` cap, and an honest empty list.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.api import app, init_db
from orchestrator.db import session_factory
from shared.persistence.models import RunRow


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    await init_db("sqlite+aiosqlite:///:memory:")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def _seed(run_id: str, *, created_at: datetime, target: str, rounds: int) -> None:
    async with session_factory()() as s:
        s.add(
            RunRow(
                id=run_id,
                seed="seed",
                status="complete",
                n_rounds=rounds,
                batch_size=40,
                threshold=0.5,
                params_json={"target": target, "rounds": rounds},
                created_at=created_at,
            )
        )
        await s.commit()


async def test_runs_empty_state(client: AsyncClient) -> None:
    r = await client.get("/runs")
    assert r.status_code == 200, r.text
    assert r.json() == {"runs": []}


async def test_runs_shape_and_newest_first(client: AsyncClient) -> None:
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    oldest = str(uuid.uuid4())
    middle = str(uuid.uuid4())
    newest = str(uuid.uuid4())
    await _seed(oldest, created_at=base, target="synth", rounds=2)
    await _seed(middle, created_at=base + timedelta(hours=1), target="sparkov", rounds=3)
    await _seed(newest, created_at=base + timedelta(hours=2), target="synth", rounds=5)

    r = await client.get("/runs")
    assert r.status_code == 200, r.text
    runs = r.json()["runs"]
    # Newest-first by created_at.
    assert [x["run_id"] for x in runs] == [newest, middle, oldest]
    # Exact per-row shape: target + rounds from params_json, iso8601 created_at.
    first = runs[0]
    assert set(first) == {"run_id", "target", "status", "created_at", "rounds"}
    assert first["target"] == "synth"
    assert first["rounds"] == 5
    assert first["status"] == "complete"
    # created_at is a parseable ISO-8601 string (SQLite drops tz on round-trip,
    # so we assert it parses, not that it carries an offset).
    assert isinstance(first["created_at"], str)
    datetime.fromisoformat(first["created_at"])


async def test_runs_limit_caps_results(client: AsyncClient) -> None:
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    for i in range(5):
        await _seed(
            str(uuid.uuid4()),
            created_at=base + timedelta(minutes=i),
            target="synth",
            rounds=3,
        )
    r = await client.get("/runs?limit=2")
    assert r.status_code == 200, r.text
    assert len(r.json()["runs"]) == 2
