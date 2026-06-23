"""Slice-15-backend: the Measure API the dashboard reads — honest metrics tiles,
verdict list + five-card detail, JSONL corpus, strategy catalog, and the SR 11-7
report — all from real persisted run data."""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from tests.conftest import FRAUD_SPEC_YAML


def _run_fraud(client: TestClient, rounds: int = 40) -> str:
    rid = client.post("/runs", json={
        "target_kind": "fraud", "shape": "shape1_ml", "spec_yaml": FRAUD_SPEC_YAML,
        "budget_rounds": rounds, "budget_dollars": 1.0,
    }).json()["runId"]
    for _ in range(200):
        if client.get(f"/runs/{rid}").json()["status"] == "complete":
            break
        time.sleep(0.05)
    return rid


def test_metrics_tiles_are_honest(client: TestClient) -> None:
    rid = _run_fraud(client)
    m = client.get("/metrics", params={"run_id": rid}).json()
    assert m["verdicts"] == 40
    assert "undetected_hack_rate" in m["tiles"]
    assert m["detail"]["producer_wrong_total"] >= 1   # held-out fired on real misses
    # White-box not run yet -> "Not yet measured" (None), never a sampled 0.0.
    assert m["tiles"]["white_box_catch_rate"] is None


def test_verdict_list_and_five_card_detail(client: TestClient) -> None:
    rid = _run_fraud(client, rounds=5)
    verdicts = client.get(f"/runs/{rid}/verdicts").json()
    assert len(verdicts) == 5
    detail = client.get(f"/verdicts/{verdicts[0]['verdictId']}").json()
    # five oracle cards: held-out, differential, metamorphic, property-fuzz, judge
    assert len(detail["votes"]) == 5
    assert all("reason" in v and "obligation" in v for v in detail["votes"])
    assert "fraud_probability" in detail["producer_output"]


def test_corpus_jsonl_and_catalog(client: TestClient) -> None:
    rid = _run_fraud(client)
    resp = client.get("/corpus", params={"run_id": rid})
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    rows = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    assert int(resp.headers["x-row-count"]) == len(rows)
    for row in rows:                                  # only undetected hacks belong here
        assert row["target_type"] == "fraud"
    catalog = client.get("/catalog", params={"run_id": rid}).json()
    assert isinstance(catalog, list)


def test_sr_11_7_report_renders_real_numbers(client: TestClient) -> None:
    rid = _run_fraud(client, rounds=10)
    report = client.get(f"/reports/{rid}")
    assert report.headers["content-type"].startswith("text/markdown")
    assert "SR 11-7 Model Risk Report" in report.text
    assert "Black-box catch rate" in report.text
    assert "Undetected-hack rate" in report.text
