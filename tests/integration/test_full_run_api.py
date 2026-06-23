"""The full-arc API test: a REAL Sparkov run end-to-end through POST /runs,
including the blue recovery arc, persisted — with ZERO real LLM calls.

The API builds components internally, so the test injects
``orchestrator.api.SPARKOV_TEST_OVERRIDES`` (mock providers + budget 0 on judge,
red, and blue) so the loop runs entirely on its FREE deterministic seams: the
metamorphic mutator drives the red loop, the mock judge abstains under budget 0,
and the mock blue proposer proposes {"features_to_add": ["hour","distance"]}.
Nothing in this path is mocked except the LLM seams — the REAL LightGBM
detector, REAL Sparkov data, REAL mutator, and REAL retraining all run.

Asserts the full red->verify->blue->recover story is persisted and exposed:
attacks + verdicts exist, a BlueRoundRow exists with detection_after >=
detection_before, GET /runs/{id}/blue returns it, and /metrics returns the
co-evolution numbers.

Skips (not fails) when the external Sparkov CSVs / artifact are absent.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

import orchestrator.api as api
from examples.targets import fraud_sparkov
from orchestrator.api import app, init_db
from shared.llm import MockProvider

_DATA_READY = (
    fraud_sparkov.constants.TEST_CSV.exists()
    and fraud_sparkov.constants.TRAIN_CSV.exists()
    and fraud_sparkov.MODEL_PATH.exists()
    and fraud_sparkov.constants.CHECKSUM_PATH.exists()
)
_SKIP_REASON = (
    "Sparkov real CSVs / trained artifact missing (gitignored external inputs); "
    "run `python -m examples.targets.fraud_sparkov.train` after placing the data."
)

# Every LLM seam neutralized: budget 0 on all three, mock providers everywhere.
# ZERO real Sonnet/Opus calls. Blue proposer proposes hour+distance (the budget-0
# deterministic fallback would propose the same unused features).
_OVERRIDES: dict[str, object] = {
    "judge_provider": MockProvider(
        text='{"per_obligation":[],"independent_finding":"fixture",'
        '"vote":"pass","reason":"fixture"}'
    ),
    "judge_max_calls": 0,
    "red_provider": MockProvider(
        text='{"feature":"amt","new_value":1.0,"rationale":"x"}'
    ),
    "red_max_calls": 0,
    "blue_provider": MockProvider(
        text='{"features_to_add":["hour","distance"],"rationale":"close blind spot"}'
    ),
    "blue_max_calls": 5,
}


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    await init_db("sqlite+aiosqlite:///:memory:")
    api.SPARKOV_TEST_OVERRIDES = _OVERRIDES
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            yield c
    finally:
        api.SPARKOV_TEST_OVERRIDES = None


@pytest.mark.skipif(not _DATA_READY, reason=_SKIP_REASON)
async def test_full_sparkov_run_with_blue_via_api(client: AsyncClient) -> None:
    r = await client.post(
        "/runs",
        json={
            "target": "sparkov",
            "rounds": 4,
            "batch_size": 80,
            "seed": "sparkov-full-arc",
            "run_blue": True,
        },
    )
    assert r.status_code == 201, r.text
    run_id = r.json()["run_id"]

    # Background task completes within the request lifecycle (ASGITransport).
    run = await client.get(f"/runs/{run_id}")
    assert run.status_code == 200, run.text
    assert run.json()["status"] == "complete", run.json()

    # Verdicts persisted (the detector let attacked samples through -> oracles voted).
    verdicts = await client.get(f"/runs/{run_id}/verdicts")
    assert verdicts.status_code == 200
    assert len(verdicts.json()["verdicts"]) > 0

    # Co-evolution metrics surface for a sparkov run (generic shape holds).
    metrics = await client.get(f"/runs/{run_id}/metrics")
    assert metrics.status_code == 200
    body = metrics.json()
    assert "per_round" in body and body["per_round"]

    # The blue recovery arc was persisted and is exposed.
    blue = await client.get(f"/runs/{run_id}/blue")
    assert blue.status_code == 200, blue.text
    b = blue.json()
    assert b["n_holdout"] > 0
    assert b["detection_after"] >= b["detection_before"]
    assert "hour" in b["features_added"]


@pytest.mark.skipif(not _DATA_READY, reason=_SKIP_REASON)
async def test_blue_404_when_no_blue_run(client: AsyncClient) -> None:
    r = await client.post(
        "/runs",
        json={
            "target": "sparkov",
            "rounds": 2,
            "batch_size": 40,
            "seed": "sparkov-no-blue",
            "run_blue": False,
        },
    )
    assert r.status_code == 201
    run_id = r.json()["run_id"]
    blue = await client.get(f"/runs/{run_id}/blue")
    assert blue.status_code == 404
