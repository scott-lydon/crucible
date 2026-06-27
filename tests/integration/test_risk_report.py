"""cr-f2 done criteria: the SR 11-7 risk report generalizes to agents (target-agnostic
ensemble description), leads with the trust score, includes a co-evolution summary when the
run hardened the agent, and renders to a real PDF — all from the run's persisted numbers."""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient


def _run(client: TestClient, payload: dict[str, Any]) -> str:
    run_id: str = client.post("/runs", json=payload).json()["runId"]
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if client.get(f"/runs/{run_id}").json()["status"] in ("complete", "failed"):
            break
        time.sleep(0.05)
    return run_id


_AGENT_RUN = {
    "target_kind": "agent", "shape": "shape2_agent", "budget_rounds": 1,
    "human_spec": {"task": "Help with orders.", "failure_conditions": ["leak customer data"]},
}
_COEVO_RUN = {**_AGENT_RUN, "mode": "coevolution", "coevo_rounds": 2, "attacks_per_round": 1}


def test_agent_report_is_target_agnostic_and_leads_with_trust(client: TestClient) -> None:
    run_id = _run(client, _AGENT_RUN)
    md = client.get(f"/reports/{run_id}").text
    assert "Trust score" in md
    assert "reference model" in md           # generalized agent ensemble, not IsolationForest
    assert "IsolationForest" not in md
    assert "agent" in md


def test_coevolution_report_includes_curve_summary(client: TestClient) -> None:
    run_id = _run(client, _COEVO_RUN)
    md = client.get(f"/reports/{run_id}").text
    assert "Co-evolution" in md
    assert "ASR" in md and "blue safe-rate" in md


def test_report_pdf(client: TestClient) -> None:
    run_id = _run(client, _AGENT_RUN)
    resp = client.get(f"/reports/{run_id}", params={"format": "pdf"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"          # a real PDF
    assert len(resp.content) > 1000


def test_report_404_unknown_run(client: TestClient) -> None:
    assert client.get("/reports/nope").status_code == 404
    assert client.get("/reports/nope", params={"format": "pdf"}).status_code == 404
