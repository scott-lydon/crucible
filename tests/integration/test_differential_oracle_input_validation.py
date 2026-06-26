"""Verification finding #3 (Gustavo / Measure lane): the differential oracle silently
neuters itself on a feature-key mismatch instead of validating its input.

``modules/oracles/differential/oracle.py:37`` builds its feature vector with
``float(payload.get(name, 0.0))`` — every expected feature that is absent from the
attack payload defaults to 0.0. So a payload whose keys do not match the model's
feature names is scored as an all-zeros vector (a "normal"-looking point), the oracle
returns ``fired=False``, and that is indistinguishable from "I evaluated this input and
found no missed-fraud disagreement." The single independent corroborator the ensemble
relies on (metamorphic/property_fuzz are quiet on well-formed, stable outputs — see the
8%-corroboration measurement in the finding write-up) is silently disabled by a schema
drift or a crafted payload, with no error and no signal.

constitution.md ("validate input at system boundaries") and QA_ADVERSARY rule 6
(exceptions must propagate; no catch-log-continue) want this to fail loud, not quiet.

First test characterises today's silent behaviour (passes); the second asserts the
boundary-validation contract and is a strict xfail until the oracle validates its keys.
"""

from __future__ import annotations

import asyncio

import pytest

from modules.oracles.differential.oracle import FraudDifferentialOracle
from shared.types.core import Attack
from shared.types.enums import Shape
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


def test_feature_key_mismatch_is_scored_as_normal_silently() -> None:
    """Characterisation: a payload sharing NO keys with the model's features is scored
    as an all-zeros vector and abstains, with no indication it could not evaluate."""
    oracle = FraudDifferentialOracle.load(1)
    vote = asyncio.run(oracle.vote(_SPEC, _attack({"unrelated_key": 9999.0}), _MISSED_FRAUD_OUTPUT))
    # The oracle reports a clean "no disagreement" — indistinguishable from a real check.
    assert vote.fired is False
    assert "diff_label=0" in vote.observation


@pytest.mark.xfail(
    strict=True,
    reason="Finding #3: the differential oracle defaults missing feature keys to 0.0, "
    "silently neutering itself on a schema mismatch. constitution 'validate input at "
    "system boundaries' wants it to raise (fail loud), not abstain silently.",
)
def test_feature_key_mismatch_must_fail_loud() -> None:
    """Desired property: given a payload that matches none of the model's expected
    features, the oracle must refuse to fabricate an all-zeros score and instead raise."""
    oracle = FraudDifferentialOracle.load(1)
    with pytest.raises(ValueError):
        asyncio.run(oracle.vote(_SPEC, _attack({"unrelated_key": 9999.0}), _MISSED_FRAUD_OUTPUT))
