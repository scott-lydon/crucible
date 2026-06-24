"""Property-fuzz BITES the REAL Sparkov detector via the night-hour invariant.

The deployed Sparkov detector is trained only on ``(amt, cat_risk)`` and is
BLIND to ``hour``. The SealedSpec's ``night_hour_must_flag`` invariant declares
the obligation it violates: every night-window transaction must be flagged
regardless of amount. This test proves the obligation BITES the REAL model:

* The property-fuzz oracle GENERATES a low-amount night-hour counterexample the
  amt-reliant detector clears -> FAIL on the REAL detector (not a fixture).
* The InvariantOracle consistently FLAGS an observed night-hour miss.

Skips (rather than fails) when the real CSV or the serialized LightGBM artifact
is absent — they are gitignored external inputs, not source. ZERO LLM calls.
"""

from collections.abc import Mapping, Sequence
from typing import cast

import pytest

from examples.targets import fraud_sparkov
from examples.targets.fraud_sparkov.record import SparkovTxn
from modules.oracles.invariant.oracle import InvariantOracle
from modules.oracles.property_fuzz.oracle import PropertyFuzzOracle
from modules.targets.local_model.adapter import LocalModelTarget
from shared.types import Vote
from shared.types.enums import OracleKind
from shared.types.verdict import VerdictContext

_THRESHOLD = fraud_sparkov.DETECTOR_THRESHOLD
_ARTIFACTS_READY = (
    fraud_sparkov.constants.TRAIN_CSV.exists()
    and fraud_sparkov.constants.CHECKSUM_PATH.exists()
    and fraud_sparkov.MODEL_PATH.exists()
)
_SKIP_REASON = (
    "Sparkov real CSV and/or serialized LightGBM artifact missing (gitignored "
    "external inputs); place the data under data/ and run train.py to exercise "
    "the property-fuzz test against the REAL detector."
)


def _real_detector() -> LocalModelTarget:
    return LocalModelTarget(
        model_path=fraud_sparkov.MODEL_PATH,
        feature_names=fraud_sparkov.DETECTOR_FEATURES,
    )


def _ctx(sample: object, detector: LocalModelTarget) -> VerdictContext:
    return VerdictContext(
        sample=sample,
        detector_score=detector.score(sample),
        threshold=_THRESHOLD,
        true_label=True,
        original_sample=None,
        original_score=None,
        spec=fraud_sparkov.load_spec(),
    )


def test_spec_declares_night_hour_invariant() -> None:
    """The night-hour blind-spot obligation is declared in the SealedSpec, and
    its hour set matches the rule's NIGHT_HOURS (single point of truth)."""
    spec = fraud_sparkov.load_spec()
    night = [i for i in spec.invariants if i.name == "night_hour_must_flag"]
    assert night, "night_hour_must_flag invariant must be declared in spec.yaml"
    all_of = cast(Sequence[Mapping[str, object]], night[0].params["all_of"])
    cond = all_of[0]
    assert cond["feature"] == "hour"
    assert set(cast(Sequence[int], cond["in_"])) == set(fraud_sparkov.NIGHT_HOURS)


@pytest.mark.skipif(not _ARTIFACTS_READY, reason=_SKIP_REASON)
def test_property_fuzz_fails_real_sparkov_on_night_hour() -> None:
    """Property-fuzz GENERATES a night-hour counterexample the REAL amt-reliant
    detector clears, FAILing it on the night_hour_must_flag invariant."""
    detector = _real_detector()
    # Any sample seeds the run-level probe; the search is over input space.
    seed_sample = SparkovTxn(
        txn_index=0, amt=10.0, cat_risk=0, hour=23, age=40, city_pop=1000
    )
    oracle = PropertyFuzzOracle(
        score_fn=detector.score,
        strategy=fraud_sparkov.sparkov_strategy(),
        max_examples=200,
        seed=8,
    )
    vote = oracle.vote(_ctx(seed_sample, detector))

    assert vote.kind is OracleKind.PROPERTY_FUZZ
    assert vote.vote is Vote.FAIL, vote.reason
    assert vote.evidence["invariant_id"] == "night_hour_must_flag"
    counterexample = vote.evidence["counterexample"]
    assert isinstance(counterexample, dict)
    # The generated counterexample is a night-hour transaction the real detector
    # cleared below threshold.
    assert counterexample["hour"] in fraud_sparkov.NIGHT_HOURS
    assert cast(float, vote.evidence["score"]) < _THRESHOLD


@pytest.mark.skipif(not _ARTIFACTS_READY, reason=_SKIP_REASON)
def test_invariant_oracle_flags_night_hour_miss_real_sparkov() -> None:
    """The InvariantOracle consistently FLAGS an observed night-hour miss the
    REAL detector clears (the same blind spot, checked rather than searched)."""
    detector = _real_detector()
    # A low-amount, non-risky-category night transaction: declared rule says
    # fraud (night hour), the amt-reliant detector clears it.
    night_miss = SparkovTxn(
        txn_index=1, amt=8.0, cat_risk=0, hour=1, age=30, city_pop=500
    )
    assert fraud_sparkov.is_fraud(night_miss) is True
    ctx = _ctx(night_miss, detector)
    assert ctx.detector_score < _THRESHOLD, ctx.detector_score

    vote = InvariantOracle().vote(ctx)
    assert vote.kind is OracleKind.INVARIANT
    assert vote.vote is Vote.FAIL, vote.reason
    assert "night_hour_must_flag" in cast(
        Sequence[str], vote.evidence["violated"]
    )
