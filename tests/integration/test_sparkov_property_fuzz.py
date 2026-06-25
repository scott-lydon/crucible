"""Property-fuzz BITES the REAL Sparkov detector via a declared invariant.

Part B1: the deployed victim is a multi-feature LightGBM over the static set
(amt, cat_risk, merchant_risk, age, city_pop), blind to the
behavioral/temporal/geo signals. The SealedSpec's ``risky_category_high_amount``
invariant declares a hard obligation: a high-amount transaction in a risky
category must be flagged. This test proves the obligation BITES the REAL model:

* The property-fuzz oracle GENERATES a high-amount risky-category counterexample
  the victim clears (e.g. one with low per-merchant risk) -> FAIL on the REAL
  detector (not a fixture).
* The InvariantOracle consistently FLAGS such an observed miss.

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
_INVARIANT = "risky_category_high_amount_must_flag"
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


def test_spec_declares_risky_category_invariant() -> None:
    """The risky-category-high-amount obligation is declared in the SealedSpec
    over the cat_risk/amt features (single point of truth), and the retired
    night-hour invariant is GONE."""
    spec = fraud_sparkov.load_spec()
    names = {i.name for i in spec.invariants}
    assert _INVARIANT in names, names
    assert "night_hour_must_flag" not in names, "night-hour invariant must be retired"
    inv = next(i for i in spec.invariants if i.name == _INVARIANT)
    all_of = cast(Sequence[Mapping[str, object]], inv.params["all_of"])
    feats = {cast(str, c["feature"]) for c in all_of}
    assert feats == {"cat_risk", "amt"}, feats


@pytest.mark.skipif(not _ARTIFACTS_READY, reason=_SKIP_REASON)
def test_property_fuzz_fails_real_sparkov_on_invariant() -> None:
    """Property-fuzz GENERATES a high-amount risky-category counterexample the
    REAL victim clears, FAILing it on the risky_category_high_amount invariant."""
    detector = _real_detector()
    seed_sample = SparkovTxn(
        txn_index=0, amt=10.0, cat_risk=1, merchant_risk=0.0, age=40, city_pop=1000
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
    assert vote.evidence["invariant_id"] == _INVARIANT
    counterexample = vote.evidence["counterexample"]
    assert isinstance(counterexample, dict)
    # The generated counterexample is a high-amount risky-category transaction the
    # real detector cleared below threshold.
    assert counterexample["cat_risk"] == 1
    assert cast(float, counterexample["amt"]) > 250
    assert cast(float, vote.evidence["score"]) < _THRESHOLD


@pytest.mark.skipif(not _ARTIFACTS_READY, reason=_SKIP_REASON)
def test_invariant_oracle_flags_miss_real_sparkov() -> None:
    """The InvariantOracle consistently FLAGS an observed high-amount
    risky-category miss the REAL detector clears (checked, not searched)."""
    detector = _real_detector()
    # A high-amount risky-category transaction with low per-merchant risk: the
    # invariant says it must be flagged; the multi-feature detector (leaning on
    # merchant_risk) clears it.
    miss = SparkovTxn(
        txn_index=1, amt=300.0, cat_risk=1, merchant_risk=0.0, age=30, city_pop=500
    )
    ctx = _ctx(miss, detector)
    assert ctx.detector_score < _THRESHOLD, ctx.detector_score

    vote = InvariantOracle().vote(ctx)
    assert vote.kind is OracleKind.INVARIANT
    assert vote.vote is Vote.FAIL, vote.reason
    assert _INVARIANT in cast(Sequence[str], vote.evidence["violated"])
