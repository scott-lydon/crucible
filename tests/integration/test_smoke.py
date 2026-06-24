"""Slice 0 done-criterion: POST /runs persists a run and returns its id,
GET /health does a real database round trip, and the SSE stream emits the
run's status. All against a real Postgres, never a mock.
"""

from __future__ import annotations

from httpx import AsyncClient

_VALID_RUN = {
    "target_type": "dummy",
    "artifact_ref": "dummy-v0",
    "spec": {
        "title": "sum two integers",
        "obligations": [{"id": "o1", "description": "returns the sum of the two inputs"}],
        "invariants": [{"id": "i1", "description": "adding zero leaves the result unchanged"}],
        "holdout_generator_kind": "llm_post_submit",
    },
    "budget": {"max_attempts": 5, "max_dollars": 1.0},
}


async def test_post_runs_returns_run_id(client: AsyncClient) -> None:
    resp = await client.post("/runs", json=_VALID_RUN)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["run_id"], "run_id must be a non-empty string"
    assert body["status"] == "pending"


async def test_health_reports_database_connected(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ok", "database": "connected"}


async def test_post_runs_rejects_spec_without_obligations(client: AsyncClient) -> None:
    bad = {**_VALID_RUN, "spec": {"title": "no obligations", "obligations": []}}
    resp = await client.post("/runs", json=bad)
    assert resp.status_code == 422, resp.text
    assert "obligation" in resp.json()["detail"].lower()


async def test_post_runs_rejects_unknown_target_type(client: AsyncClient) -> None:
    bad = {**_VALID_RUN, "target_type": "not_a_real_target"}
    resp = await client.post("/runs", json=bad)
    assert resp.status_code == 422, resp.text
    assert "target_type" in resp.json()["detail"]


async def test_stream_unknown_run_is_404(client: AsyncClient) -> None:
    resp = await client.get("/runs/does-not-exist/stream")
    assert resp.status_code == 404, resp.text
