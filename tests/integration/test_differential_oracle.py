"""Slice-7 done criteria: the differential oracle (LightGBM vs IsolationForest) votes
correctly — it fires when an independent model flags fraud the producer missed, stays
silent on agreement, and has a low false-positive rate on legitimate transactions. It
never trusts a single side as ground truth (it is one vote of four)."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from modules.oracles.differential.model import ensure_isoforest
from modules.oracles.differential.oracle import FraudDifferentialOracle
from modules.targets.fraud.target import FraudTarget
from shared.datasets.fraud import load_splits
from shared.types.core import Attack
from shared.types.enums import OracleKind, Shape
from shared.types.ids import AttackId, RunId
from shared.types.sealed_spec import Obligation, SealedSpec

_SPEC = SealedSpec(
    spec_id="s", target_kind="fraud", shape=Shape.shape1_ml,
    obligations=(
        Obligation("catch-fraud", "A fraudulent transaction must score above the threshold.",
                   "label_match", {}),
    ),
    invariants=(), holdout_generator_kind="data_partition",
)


def _attack(payload: Mapping[str, Any]) -> Attack:
    return Attack(AttackId("a"), RunId("r"), 0, "t", dict(payload), "", "seed")


def test_differential_fire_logic() -> None:
    ensure_isoforest(1)
    oracle = FraudDifferentialOracle.load(1)
    splits = load_splits()

    anomalous: dict[str, Any] | None = None
    normal: dict[str, Any] | None = None
    for idx in splits.x_holdout.index[:3000]:
        row = splits.x_holdout.loc[idx].to_dict()
        score = oracle._anomaly_score(row)
        if score >= oracle._threshold and anomalous is None:
            anomalous = row
        elif score < oracle._threshold and normal is None:
            normal = row
        if anomalous is not None and normal is not None:
            break
    assert anomalous is not None and normal is not None

    # Anomalous input + producer said legit -> fires (missed fraud), with full reasoning.
    missed = {"label": 0, "fraud_probability": 0.1}
    fired = asyncio.run(oracle.vote(_SPEC, _attack(anomalous), missed))
    assert fired.fired is True
    assert fired.oracle is OracleKind.differential
    assert fired.weight == 1.0
    assert fired.obligation.startswith("A fraudulent transaction")
    assert "IsolationForest" in fired.reason

    # Anomalous input but the producer already caught it (label 1) -> no missed-fraud, silent.
    got = {"label": 1, "fraud_probability": 0.9}
    caught = asyncio.run(oracle.vote(_SPEC, _attack(anomalous), got))
    assert caught.fired is False

    # Normal input + producer legit -> agreement, silent.
    agree = asyncio.run(oracle.vote(_SPEC, _attack(normal), {"label": 0}))
    assert agree.fired is False


def test_differential_low_false_positive_on_legit() -> None:
    ensure_isoforest(1)
    oracle = FraudDifferentialOracle.load(1)
    target = FraudTarget.load(1)
    splits = load_splits()

    async def fire_rate() -> float:
        fired = 0
        idxs = splits.y_holdout[splits.y_holdout == 0].index[:300]
        for idx in idxs:
            row = splits.x_holdout.loc[idx].to_dict()
            output = (await target.submit(row)).output
            vote = await oracle.vote(_SPEC, _attack(row), output)
            fired += int(vote.fired)
        return fired / len(idxs)

    assert asyncio.run(fire_rate()) < 0.05  # one noisy vote of four; aggregator needs 2.0


def test_differential_health_green() -> None:
    ensure_isoforest(1)
    oracle = FraudDifferentialOracle.load(1)
    health = asyncio.run(oracle.health())
    assert health.status == "green"
    assert health.detail["family"] == "IsolationForest"
