from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient, ASGITransport

from orchestrator.api import app, init_db
from orchestrator.db import session_factory
from shared.persistence import repo
from shared.persistence.models import RunRow


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    await init_db("sqlite+aiosqlite:///:memory:")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def test_health_ok(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    # /health is now the hierarchical self-test view (US-8) + seal card (US-9):
    # pillar -> module -> subcomponent, plus the producer-sandbox seal card.
    assert "pillars" in body and body["pillars"]
    assert {p["pillar_id"] for p in body["pillars"]} >= {
        "targets", "red", "blue", "measure", "external_deps"
    }
    assert body["seal_card"]["egress_allow_list"] == []


async def test_post_run_then_metrics(client: AsyncClient) -> None:
    r = await client.post(
        "/runs",
        json={"target": "synth", "rounds": 5, "batch_size": 200,
              "seed": "seed-1", "run_blue": False},
    )
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


async def test_llm_calls_inspect_endpoints(client: AsyncClient) -> None:
    # Seed a run + one recorded LLM call directly (US-2/US-3 Inspect data).
    sf = session_factory()
    async with sf() as s:
        s.add(RunRow(id="r-insp", seed="s", status="complete", n_rounds=2,
                     batch_size=4, threshold=0.5, params_json={}))
        await s.commit()
        call_id = await repo.record_llm_call(
            s, run_id="r-insp", pillar="judge", model="claude-opus-4-8",
            prompt="P" * 300, system="be terse",
            raw_response='{"id":"resp_1"}', parsed_output='{"vote":"fail"}',
            input_tokens=1000, output_tokens=500, dollars=0.0175,
        )

    # List endpoint: one row, prompt PREVIEW (truncated), token/dollar summary.
    lst = await client.get("/runs/r-insp/llm_calls")
    assert lst.status_code == 200
    body = lst.json()
    assert body["count"] == 1
    item = body["llm_calls"][0]
    assert item["id"] == call_id
    assert item["pillar"] == "judge"
    assert item["dollars"] == 0.0175
    assert len(item["prompt_preview"]) < 300  # truncated preview

    # Full record endpoint: the FULL prompt/system/raw/parsed the Inspect button opens.
    full = await client.get(f"/llm_calls/{call_id}")
    assert full.status_code == 200
    f = full.json()
    assert f["prompt"] == "P" * 300
    assert f["system"] == "be terse"
    assert f["raw_response"] == '{"id":"resp_1"}'
    assert f["parsed_output"] == '{"vote":"fail"}'
    assert f["input_tokens"] == 1000 and f["output_tokens"] == 500


async def test_llm_call_404_for_unknown(client: AsyncClient) -> None:
    r = await client.get("/llm_calls/nope")
    assert r.status_code == 404


async def test_metrics_exposes_cost_tiles(client: AsyncClient) -> None:
    r = await client.post(
        "/runs",
        json={"target": "synth", "rounds": 5, "batch_size": 200,
              "seed": "seed-1", "run_blue": False},
    )
    assert r.status_code == 201
    run_id = r.json()["run_id"]
    body = (await client.get(f"/runs/{run_id}/metrics")).json()
    # synth records no LLM calls -> dollars tile is honest None (not 0.0).
    assert body["dollars_per_caught_hack"] is None
    # No human-review signal in the system -> honestly Not yet measured (None).
    assert body["human_minutes_per_1k_outputs"] is None


async def test_list_verdicts(client: AsyncClient) -> None:
    r = await client.post(
        "/runs",
        json={"target": "synth", "rounds": 5, "batch_size": 200,
              "seed": "seed-1", "run_blue": False},
    )
    assert r.status_code == 201
    run_id = r.json()["run_id"]
    v = await client.get(f"/runs/{run_id}/verdicts")
    assert v.status_code == 200
    body = v.json()
    verdicts = body["verdicts"]
    assert isinstance(verdicts, list) and len(verdicts) > 0
    for item in verdicts:
        assert "verdict_id" in item
        assert "aggregate_pass" in item
        assert "fail_weight" in item
