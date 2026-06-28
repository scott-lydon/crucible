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


# ----------------------------- D2 -----------------------------

def test_d2_white_box_brief_lists_the_wired_oracles(client: TestClient) -> None:
    brief = client.get("/white-box-brief", params={"target_kind": "fraud"}).json()
    # The full fraud panel is the four mechanical oracles + the LLM judge.
    assert brief["oracles"] == [
        "Held-out oracle", "Metamorphic oracle", "Differential oracle",
        "Property / fuzz oracle", "LLM judge oracle",
    ]
    assert "WHITE-BOX" in brief["brief"]
    assert "LLM judge oracle" in brief["brief"]


def test_d2_compose_brief_is_one_line_per_oracle() -> None:
    from modules.red.white_box import compose_white_box_brief
    protocols = [
        {"kind": "held_out", "name": "Held-out oracle", "description": "checks ground truth"},
        {"kind": "differential", "name": "Differential oracle", "description": "a second model"},
    ]
    brief = compose_white_box_brief(protocols)
    lines = [ln for ln in brief.splitlines() if ln.startswith("- ")]
    assert len(lines) == 2
    assert "LLM judge" not in brief  # only the wired oracles appear
