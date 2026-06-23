from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient, ASGITransport
from orchestrator.api import app, init_db


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    await init_db("sqlite+aiosqlite:///:memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_full_run_tells_the_story(client: AsyncClient) -> None:
    r = await client.post(
        "/runs",
        json={"target": "synth", "rounds": 5, "batch_size": 200,
              "seed": "story", "run_blue": False},
    )
    assert r.status_code == 201
    run_id = r.json()["run_id"]
    body = (await client.get(f"/runs/{run_id}/metrics")).json()
    per = body["per_round"]
    dets = [x["detection_rate"] for x in per if x["detection_rate"] is not None]
    evas = [x["evasion_rate"] for x in per if x["evasion_rate"] is not None]
    asrs = [x["asr"] for x in per if x["asr"] is not None]
    assert dets[-1] <= dets[0]          # detection falls
    assert evas[-1] >= evas[0]          # evasion climbs (co-evolution)
    assert asrs and asrs[0] == 1.0      # round-0 attack success is real
    assert body["gap"] is not None and body["gap"] > 0   # silent-wrongness gap
