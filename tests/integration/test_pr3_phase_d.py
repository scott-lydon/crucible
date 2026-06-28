"""PR #3 -> main port, Phase D (red + catalog richness).

D1 the run drives two distinct red passes (black-box then white-box); verdicts carry the
   pass they belong to, so the live-run view can label them separately.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from tests.conftest import FRAUD_SPEC_YAML


def _poll_complete(client: TestClient, run_id: str, timeout: float = 30.0) -> str:
    deadline = time.time() + timeout
    status = ""
    while time.time() < deadline:
        status = client.get(f"/runs/{run_id}").json()["status"]
        if status in ("complete", "failed"):
            return status
        time.sleep(0.1)
    return status


def test_d1_run_has_both_black_box_and_white_box_passes(client: TestClient) -> None:
    resp = client.post("/runs", json={
        "target_kind": "fraud", "shape": "shape1_ml",
        "spec_yaml": FRAUD_SPEC_YAML, "budget_rounds": 2, "budget_dollars": 1.0,
    })
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["runId"]
    assert _poll_complete(client, run_id) == "complete"

    verdicts = client.get(f"/runs/{run_id}/verdicts").json()
    passes = {v["white_box"] for v in verdicts}
    assert passes == {True, False}, f"expected both passes, got {passes}"
