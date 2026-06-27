"""Slice-0 done criteria: POST /runs returns a run id; the run lifecycle completes;
/health surfaces the persistence probe; a malformed spec is a typed 422."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from tests.conftest import DUMMY_SPEC_YAML


def _poll_status(client: TestClient, run_id: str, target: str, timeout: float = 5.0) -> str:
    deadline = time.time() + timeout
    status: str = ""
    while time.time() < deadline:
        body = client.get(f"/runs/{run_id}").json()
        status = body["status"]
        if status == target:
            return status
        time.sleep(0.05)
    return status


def test_post_runs_returns_run_id(client: TestClient) -> None:
    resp = client.post(
        "/runs",
        json={
            "target_kind": "dummy",
            "shape": "shape1_ml",
            "spec_yaml": DUMMY_SPEC_YAML,
            "budget_rounds": 3,
            "budget_dollars": 1.0,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["runId"].startswith("run_")
    assert body["status"] == "pending"

    # The background loop drives the run to completion through the dummy target.
    assert _poll_status(client, body["runId"], "complete") == "complete"


def test_health_reports_persistence_green(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    health = resp.json()
    assert "shared/persistence" in health
    assert health["shared/persistence"]["status"] == "green"


def test_invalid_spec_is_422(client: TestClient) -> None:
    resp = client.post(
        "/runs",
        json={
            "target_kind": "fraud",
            "shape": "shape1_ml",
            "spec_yaml": "this: is: not: a: valid: spec",
            "budget_rounds": 3,
            "budget_dollars": 1.0,
        },
    )
    assert resp.status_code == 422
