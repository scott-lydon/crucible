"""Slice-15-backend: the Measure API the dashboard reads — honest metrics tiles,
verdict list + five-card detail, JSONL corpus, strategy catalog, and the SR 11-7
report — all from real persisted run data."""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from tests.conftest import FRAUD_SPEC_YAML


def _run_fraud(client: TestClient, rounds: int = 15) -> str:
    rid: str = client.post("/runs", json={
        "target_kind": "fraud", "shape": "shape1_ml", "spec_yaml": FRAUD_SPEC_YAML,
        "budget_rounds": rounds, "budget_dollars": 1.0,
    }).json()["runId"]
    for _ in range(600):
        if client.get(f"/runs/{rid}").json()["status"] == "complete":
            break
        time.sleep(0.05)
    return rid


def test_metrics_tiles_are_honest(client: TestClient) -> None:
    rid = _run_fraud(client)
    m = client.get("/metrics", params={"run_id": rid}).json()
    assert m["verdicts"] == 30                        # 15 black-box + 15 white-box
    assert "undetected_hack_rate" in m["tiles"]
    assert m["detail"]["producer_wrong_total"] >= 1   # held-out fired on real misses
    # The white-box self-test always runs, so this tile is measured (a float, not None).
    assert isinstance(m["tiles"]["white_box_catch_rate"], float)
    assert "halt" in m


def test_verdict_list_and_five_card_detail(client: TestClient) -> None:
    rid = _run_fraud(client, rounds=5)
    verdicts = client.get(f"/runs/{rid}/verdicts").json()
    assert len(verdicts) == 10                        # 5 black-box + 5 white-box
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
    rid = _run_fraud(client, rounds=6)
    report = client.get(f"/reports/{rid}")
    assert report.headers["content-type"].startswith("text/markdown")
    assert "SR 11-7 Model Risk Report" in report.text
    assert "Black-box catch rate" in report.text
    assert "Undetected-hack rate" in report.text


def test_halt_certification_blocks_new_runs(client: TestClient) -> None:
    # A completed run sets a white-box recall below the 0.7 red line (the fraud
    # verifier's honest recall is low), so certification halts (spec US-13).
    _run_fraud(client, rounds=20)
    halt = client.get("/halt").json()
    assert halt["halted"] is True
    assert halt["white_box_recall"] < halt["threshold"]
    # New run-launch requests are refused with 409 + a typed message.
    resp = client.post("/runs", json={
        "target_kind": "fraud", "shape": "shape1_ml", "spec_yaml": FRAUD_SPEC_YAML,
        "budget_rounds": 2, "budget_dollars": 1.0,
    })
    assert resp.status_code == 409
    assert "halted" in resp.json()["detail"].lower()
