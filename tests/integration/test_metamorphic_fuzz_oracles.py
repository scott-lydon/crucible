"""Slices 6 + 8: the metamorphic oracle fires when a semantically-neutral transform
flips the producer's label (unstable decision), and the property-fuzz oracle fires
when the producer violates an output invariant — both stay silent on a sound producer
and fire on a broken one (the non-colluding diversity the ensemble needs)."""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Mapping
from typing import Any

from modules.oracles.metamorphic.oracle import FraudMetamorphicOracle
from modules.oracles.property_fuzz.oracle import FraudPropertyFuzzOracle
from modules.targets.fraud.target import FraudTarget
from shared.datasets.fraud import load_splits
from shared.types.core import Attack
from shared.types.enums import Shape
from shared.types.ids import AttackId, RunId
from shared.types.sealed_spec import Obligation, SealedSpec

_SPEC = SealedSpec(
    spec_id="s", target_kind="fraud", shape=Shape.shape1_ml,
    obligations=(Obligation("catch-fraud", "A fraudulent transaction must score high.",
                            "label_match", {}),),
    invariants=(), holdout_generator_kind="data_partition",
)


def _attack(payload: Mapping[str, Any]) -> Attack:
    return Attack(AttackId("a"), RunId("r"), 0, "t", dict(payload), "", "seed-x")


# ---- metamorphic ----

def test_metamorphic_silent_on_stable_producer() -> None:
    oracle = FraudMetamorphicOracle(lambda _p: {"fraud_probability": 0.9, "label": 1},
                                    ["Amount", "V1"])
    vote = asyncio.run(oracle.vote(_SPEC, _attack({"Amount": 100.0, "V1": 0.5}), {"label": 1}))
    assert vote.fired is False
    assert "rules_checked=3" in vote.observation


def test_metamorphic_fires_on_unstable_producer() -> None:
    # Label hinges sharply on Amount near 100 -> the +1% scaling transform flips it.
    oracle = FraudMetamorphicOracle(
        lambda p: {"fraud_probability": 0.5, "label": 1 if p["Amount"] > 100 else 0},
        ["Amount"])
    vote = asyncio.run(oracle.vote(_SPEC, _attack({"Amount": 100.0}), {"label": 0}))
    assert vote.fired is True
    assert "violated" in vote.reason.lower()


def test_metamorphic_is_deterministic() -> None:
    oracle = FraudMetamorphicOracle(
        lambda p: {"fraud_probability": 0.5, "label": 1 if p["Amount"] > 100 else 0}, ["Amount"])
    a = asyncio.run(oracle.vote(_SPEC, _attack({"Amount": 100.0}), {"label": 0}))
    b = asyncio.run(oracle.vote(_SPEC, _attack({"Amount": 100.0}), {"label": 0}))
    assert a.fired == b.fired and a.observation == b.observation


# ---- property-fuzz ----

def test_fuzz_silent_on_sound_producer() -> None:
    target = FraudTarget.load(1)
    splits = load_splits()
    row = {k: float(v) for k, v in splits.x_holdout.iloc[0].to_dict().items()}
    output = target.predict_sync(row)
    oracle = FraudPropertyFuzzOracle(target.predict_sync, target.feature_names)
    vote = asyncio.run(oracle.vote(_SPEC, _attack(row), output))
    assert vote.fired is False


def test_fuzz_fires_on_out_of_range_probability() -> None:
    oracle = FraudPropertyFuzzOracle(lambda _p: {"fraud_probability": 2.0, "label": 0},
                                     ["Amount", "V1"])
    vote = asyncio.run(oracle.vote(_SPEC, _attack({"Amount": 1.0, "V1": 0.0}),
                                   {"fraud_probability": 2.0, "label": 0}))
    assert vote.fired is True
    assert "out of [0,1]" in vote.reason


def test_fuzz_fires_on_nondeterministic_producer() -> None:
    counter = itertools.count()
    oracle = FraudPropertyFuzzOracle(
        lambda _p: {"fraud_probability": 0.5, "label": next(counter) % 2}, ["Amount", "V1"])
    vote = asyncio.run(oracle.vote(_SPEC, _attack({"Amount": 1.0, "V1": 0.0}),
                                   {"fraud_probability": 0.5, "label": 0}))
    assert vote.fired is True
    assert "non-deterministic" in vote.reason
