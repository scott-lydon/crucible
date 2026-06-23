from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient, ASGITransport

from orchestrator.api import app, init_db


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    await init_db("sqlite+aiosqlite:///:memory:")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def test_health_ok(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


async def test_post_run_then_metrics(client: AsyncClient) -> None:
    r = await client.post("/runs", json={"n_rounds": 5, "batch_size": 200, "seed": "seed-1"})
    assert r.status_code == 201
    run_id = r.json()["run_id"]
    m = await client.get(f"/runs/{run_id}/metrics")
    assert m.status_code == 200
    body = m.json()
    per = body["per_round"]
    # detection falls, evasion climbs (co-evolution), gap is a real positive number
    assert per[-1]["detection_rate"] <= per[0]["detection_rate"]
    assert per[-1]["evasion_rate"] >= per[0]["evasion_rate"]
    assert body["gap"] is not None and body["gap"] > 0
    # ASR per attempt: round 0 is a real evasion-success rate
    assert per[0]["asr"] == 1.0


async def test_metrics_not_yet_measured(client: AsyncClient) -> None:
    m = await client.get("/runs/does-not-exist/metrics")
    assert m.status_code == 200 and m.json() == {"status": "Not yet measured"}
