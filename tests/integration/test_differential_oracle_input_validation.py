"""Issue #6 (Gustavo / Measure lane) — FIXED: the differential oracle now validates its
input at the boundary instead of silently 0-filling a feature-key mismatch.

``modules/oracles/differential/oracle.py`` previously built its feature vector with
``float(payload.get(name, 0.0))`` — every absent feature defaulted to 0.0, so a payload
whose keys did not match the model's feature names was scored as an all-zeros vector
and the oracle abstained, indistinguishable from a real "no missed-fraud disagreement".
The only independent corroborator the ensemble relies on could be neutered by schema
drift or a crafted payload with no error and no signal.

The oracle now raises ``ValueError`` when expected features are absent (constitution
"validate input at system boundaries"; QA_ADVERSARY rule 6 — fail loud, propagate).
"""

from __future__ import annotations

import asyncio

import pytest

from modules.oracles.differential.oracle import FraudDifferentialOracle
from shared.datasets.fraud import load_splits
from shared.types.core import Attack
from shared.types.enums import OracleKind, Shape
from shared.types.ids import AttackId, RunId
from shared.types.sealed_spec import Obligation, SealedSpec

_SPEC = SealedSpec(
    spec_id="s", target_kind="fraud", shape=Shape.shape1_ml,
    obligations=(Obligation("catch-fraud", "fraud must score high", "label_match", {}),),
    invariants=(), holdout_generator_kind="data_partition",
)
_MISSED_FRAUD_OUTPUT = {"label": 0, "fraud_probability": 0.0}  # producer says "legit"


def _attack(payload: dict) -> Attack:
    return Attack(AttackId("a"), RunId("r"), 0, "t", payload, "", "seed")


def test_feature_key_mismatch_fails_loud() -> None:
    """A payload that carries none of the model's features raises, rather than silently
    scoring an all-zeros vector and abstaining."""
    oracle = FraudDifferentialOracle.load(1)
    with pytest.raises(ValueError, match="missing"):
        asyncio.run(oracle.vote(_SPEC, _attack({"unrelated_key": 9999.0}), _MISSED_FRAUD_OUTPUT))


def test_full_feature_payload_still_scores() -> None:
    """Regression: a well-formed feature row is still evaluated normally (no false raise)."""
    oracle = FraudDifferentialOracle.load(1)
    splits = load_splits()
    fraud_row = splits.x_holdout.iloc[splits.y_holdout.tolist().index(1)].to_dict()
    vote = asyncio.run(oracle.vote(_SPEC, _attack(fraud_row), _MISSED_FRAUD_OUTPUT))
    assert vote.oracle is OracleKind.differential
    assert isinstance(vote.fired, bool)
