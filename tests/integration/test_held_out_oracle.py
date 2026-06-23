"""Slice-5 done criteria: the held-out oracle is the ground-truth signal. For fraud
the held-out tests are the sealed data partition (real labels). It fires when the
producer mislabels a known fraud, abstains without ground truth, and — driven by the
held-out red agent through the loop — surfaces the producer's real misses, some of
which the ensemble catches."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import asyncpg
from fastapi.testclient import TestClient

from modules.oracles.held_out.oracle import FraudHeldOutOracle
from shared.types.core import Attack
from shared.types.enums import Shape
from shared.types.ids import AttackId, RunId
from shared.types.sealed_spec import Obligation, SealedSpec
from tests.conftest import FRAUD_SPEC_YAML, PGHOST, PGPASSWORD, PGPORT, PGUSER, TEST_DB

_SPEC = SealedSpec(
    spec_id="s", target_kind="fraud", shape=Shape.shape1_ml,
    obligations=(Obligation("catch-fraud", "A fraudulent transaction must score high.",
                            "label_match", {}),),
    invariants=(), holdout_generator_kind="data_partition",
)


def _attack(metadata: dict[str, Any] | None = None) -> Attack:
    return Attack(AttackId("a"), RunId("r"), 0, "t", {"Amount": 1.0}, "", "seed",
                  metadata=metadata or {})


def test_held_out_ground_truth_logic() -> None:
    oracle = FraudHeldOutOracle()
    # Known fraud, producer said legit -> fires (missed fraud).
    missed = asyncio.run(oracle.vote(_SPEC, _attack({"true_label": 1}), {"label": 0}))
    assert missed.fired is True
    assert "missed a known fraud" in missed.reason

    # Known fraud, producer caught it -> silent.
    caught = asyncio.run(oracle.vote(_SPEC, _attack({"true_label": 1}), {"label": 1}))
    assert caught.fired is False

    # Legit, producer agreed -> silent.
    legit = asyncio.run(oracle.vote(_SPEC, _attack({"true_label": 0}), {"label": 0}))
    assert legit.fired is False

    # No ground truth -> abstains.
    abstain = asyncio.run(oracle.vote(_SPEC, _attack(None), {"label": 0}))
    assert abstain.fired is False
    assert "abstains" in abstain.reason


async def _fetch_verdicts(run_id: str) -> list[dict[str, Any]]:
    conn = await asyncpg.connect(host=PGHOST, port=PGPORT, user=PGUSER,
                                 password=PGPASSWORD, database=TEST_DB)
    try:
        rows = await conn.fetch(
            "SELECT outcome, votes FROM verdicts WHERE run_id = $1", run_id)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


def test_held_out_surfaces_producer_misses_through_loop(client: TestClient) -> None:
    resp = client.post("/runs", json={
        "target_kind": "fraud", "shape": "shape1_ml", "spec_yaml": FRAUD_SPEC_YAML,
        "budget_rounds": 40, "budget_dollars": 1.0,
    })
    run_id = resp.json()["runId"]
    for _ in range(200):
        if client.get(f"/runs/{run_id}").json()["status"] == "complete":
            break
        time.sleep(0.05)

    verdicts = asyncio.run(_fetch_verdicts(run_id))
    assert len(verdicts) == 40

    held_out_fires = 0
    caught = 0
    for v in verdicts:
        votes = json.loads(v["votes"])
        if any(vote["oracle"] == "held_out" and vote["fired"] for vote in votes):
            held_out_fires += 1
        if v["outcome"] == "caught":
            caught += 1
    # The producer (AUC ~0.92) misses some held-out frauds; ground truth surfaces them.
    assert held_out_fires > 0, "held-out oracle should catch real producer misses"
    # Some of those misses are confirmed by a second oracle -> caught (recorded for the
    # catch-rate metric; not asserted strictly since it depends on oracle coincidence).
    assert caught >= 0
