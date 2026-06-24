from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.api import app, init_db, session_factory
from shared.persistence import repo


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    await init_db("sqlite+aiosqlite:///:memory:")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def test_corpus_count_equals_jsonl_lines(client: AsyncClient) -> None:
    r = await client.post("/runs", json={"target": "synth", "rounds": 5,
                          "batch_size": 200, "seed": "seed-1", "run_blue": False})
    assert r.status_code == 201
    table = await client.get("/corpus")
    assert table.status_code == 200
    count = table.json()["count"]
    export = await client.get("/corpus/export")
    assert export.status_code == 200
    lines = [ln for ln in export.text.split("\n") if ln]
    assert len(lines) == count  # US-11 invariant at the HTTP boundary


async def test_report_renders_for_real_run(client: AsyncClient) -> None:
    r = await client.post("/runs", json={"target": "synth", "rounds": 5,
                          "batch_size": 200, "seed": "seed-1", "run_blue": False})
    run_id = r.json()["run_id"]
    rep = await client.get(f"/reports/{run_id}")
    assert rep.status_code == 200
    assert "SR 11-7" in rep.text and f"[run:{run_id}]" in rep.text


async def test_report_404_for_missing_run(client: AsyncClient) -> None:
    assert (await client.get("/reports/nope")).status_code == 404


async def test_halt_refuses_new_runs_with_typed_409(client: AsyncClient) -> None:
    # Persist a HALTED state (recall below the red line) directly.
    async with session_factory()() as s:
        await repo.set_halt_state(s, halted=True, recall=0.40, threshold=0.70,
                                  source_run_id="wb")
    r = await client.post("/runs", json={"target": "synth", "rounds": 5,
                          "batch_size": 200, "seed": "seed-1", "run_blue": False})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["error"] == "certification_halted"
    assert detail["recall"] == 0.40
    assert detail["threshold"] == 0.70


async def test_launch_proceeds_when_not_halted(client: AsyncClient) -> None:
    async with session_factory()() as s:
        await repo.set_halt_state(s, halted=False, recall=0.85, threshold=0.70,
                                  source_run_id="wb")
    r = await client.post("/runs", json={"target": "synth", "rounds": 5,
                          "batch_size": 200, "seed": "seed-1", "run_blue": False})
    assert r.status_code == 201
    halt = await client.get("/halt")
    assert halt.status_code == 200 and halt.json()["halted"] is False
