"""US-6 / slice-11: the persisted strategy catalog + GET /catalog.

In-memory SQLite, ZERO real LLM calls. Asserts that a run with a successful
evasion persists a catalog row that surfaces through GET /catalog with the US-6
columns, that a repeated tactic increments reuse_count (never a duplicate row),
that the average dollars-to-succeed is honest (None when no cost was recorded),
and that an empty catalog returns an empty list.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.api import app, init_db
from orchestrator.db import session_factory
from orchestrator.full_run import record_strategies
from shared.persistence import repo


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    await init_db("sqlite+aiosqlite:///:memory:")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def test_empty_catalog_is_empty_list(client: AsyncClient) -> None:
    r = await client.get("/catalog")
    assert r.status_code == 200
    assert r.json() == {"count": 0, "rows": []}


async def test_successful_evasion_persists_and_surfaces_in_catalog(
    client: AsyncClient,
) -> None:
    # A synth run lands real successful evasions (no LLM); its black-box path
    # records strategies into the persisted catalog via record_strategies.
    r = await client.post(
        "/runs",
        json={"target": "synth", "rounds": 5, "batch_size": 200,
              "seed": "seed-1", "run_blue": False},
    )
    assert r.status_code == 201
    run_id = r.json()["run_id"]

    # The corpus has at least one successful evasion for this run.
    corpus = (await client.get("/corpus")).json()
    assert corpus["count"] >= 1

    cat = await client.get("/catalog")
    assert cat.status_code == 200
    body = cat.json()
    assert body["count"] >= 1
    row = body["rows"][0]
    assert set(row) == {
        "tactic",
        "target_type",
        "first_discovered_run",
        "reuse_count",
        "avg_dollars_to_succeed",
    }
    assert row["target_type"] == "synth"
    assert row["first_discovered_run"] == run_id
    assert row["reuse_count"] >= 1


async def test_repeated_tactic_increments_reuse_count_not_duplicate() -> None:
    await init_db("sqlite+aiosqlite:///:memory:")
    async with session_factory()() as s:
        await repo.record_strategy(
            s, tactic="amt:down", target_type="synth", run_id="run-1", dollars=100.0
        )
        await repo.record_strategy(
            s, tactic="amt:down", target_type="synth", run_id="run-2", dollars=300.0
        )
        rows = await repo.catalog_entries(s)
    assert len(rows) == 1  # one row, not two
    row = rows[0]
    assert row.reuse_count == 2
    assert row.first_run_id == "run-1"  # first sighting seeds the row
    assert row.total_dollars == 400.0
    assert row.dollars_samples == 2


async def test_avg_dollars_honest_none_when_no_cost() -> None:
    await init_db("sqlite+aiosqlite:///:memory:")
    async with session_factory()() as s:
        await repo.record_strategy(
            s, tactic="cat_risk:down", target_type="synth", run_id="r", dollars=0.0
        )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        rows = (await c.get("/catalog")).json()["rows"]
    assert len(rows) == 1
    assert rows[0]["reuse_count"] == 1
    assert rows[0]["avg_dollars_to_succeed"] is None  # no cost data => honest None


async def test_avg_dollars_computed_when_cost_recorded() -> None:
    await init_db("sqlite+aiosqlite:///:memory:")
    async with session_factory()() as s:
        await repo.record_strategy(
            s, tactic="amt:down", target_type="synth", run_id="r1", dollars=100.0
        )
        await repo.record_strategy(
            s, tactic="amt:down", target_type="synth", run_id="r2", dollars=300.0
        )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        rows = (await c.get("/catalog")).json()["rows"]
    assert rows[0]["avg_dollars_to_succeed"] == 200.0  # (100+300)/2 samples


async def test_target_type_filter() -> None:
    await init_db("sqlite+aiosqlite:///:memory:")
    async with session_factory()() as s:
        await repo.record_strategy(
            s, tactic="amt:down", target_type="synth", run_id="r1", dollars=0.0
        )
        await repo.record_strategy(
            s, tactic="amt:down", target_type="sparkov", run_id="r2", dollars=0.0
        )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        synth = (await c.get("/catalog", params={"target_type": "synth"})).json()
        all_rows = (await c.get("/catalog")).json()
    assert synth["count"] == 1
    assert synth["rows"][0]["target_type"] == "synth"
    assert all_rows["count"] == 2


async def test_record_strategies_helper_persists_from_run() -> None:
    """record_strategies derives catalog rows from a run's corpus entries."""
    await init_db("sqlite+aiosqlite:///:memory:")
    sf = session_factory()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/runs",
            json={"target": "synth", "rounds": 5, "batch_size": 200,
                  "seed": "seed-1", "run_blue": False},
        )
        run_id = r.json()["run_id"]
        before = (await c.get("/catalog")).json()["count"]
        # Re-recording the same run's evasions must NOT create duplicate tactics:
        # it bumps reuse_count on the existing rows only.
        await record_strategies(sf, run_id)
        after = (await c.get("/catalog")).json()["count"]
    assert before >= 1
    assert after == before  # same distinct tactics, no new rows
