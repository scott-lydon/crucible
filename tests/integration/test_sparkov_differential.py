"""REAL cross-family disagreement on the Sparkov victim (Part B1).

Proves the differential oracle's second opinion is genuine: an unsupervised
sklearn IsolationForest (a different model family) trained on the REAL Sparkov
data over the FULL rich feature set flags a behavioral-anomaly transaction (high
transaction velocity, off-hour) that the deployed multi-feature LightGBM victim —
blind to those behavioral/temporal signals — CLEARS. That disagreement is exactly
what the differential oracle turns into a FAIL vote: a real cross-family catch on
a signal the victim never engineered, nothing mocked.

Skips (rather than fails) when the external CSVs are absent — they are gitignored
inputs, not source. The IsolationForest artifact is built on demand if missing
(deterministic, seeded), so the test is self-contained and fast.
"""

import pytest

from examples.targets import fraud_sparkov
from examples.targets.fraud_sparkov import second_model
from examples.targets.fraud_sparkov.record import SparkovTxn
from modules.oracles.differential.oracle import DifferentialOracle
from modules.targets.local_model.adapter import LocalModelTarget
from shared.types import Vote
from shared.types.enums import OracleKind
from shared.types.verdict import VerdictContext

_DATA_READY = (
    fraud_sparkov.constants.TRAIN_CSV.exists()
    and fraud_sparkov.constants.CHECKSUM_PATH.exists()
)
_SKIP_REASON = (
    "Sparkov real CSV missing (gitignored external input); place it under the "
    "victim's data/ directory to run the cross-family differential test."
)

_THRESHOLD = fraud_sparkov.DETECTOR_THRESHOLD


@pytest.fixture(scope="module")
def _ensure_isoforest() -> None:
    if not second_model.SECOND_MODEL_PATH.exists():
        second_model.train_and_serialize()


@pytest.mark.skipif(not _DATA_READY, reason=_SKIP_REASON)
def test_isoforest_flags_behavioral_evasion_lightgbm_clears(
    _ensure_isoforest: None,
) -> None:
    # A low-amount but high-VELOCITY, off-hour transaction: the static-only victim
    # clears it (low amt, no behavioral signal), and the cross-family
    # IsolationForest — which sees velocity/hour — flags it as anomalous.
    evasion = SparkovTxn(
        txn_index=0,
        amt=12.0,
        cat_risk=0,
        merchant_risk=0.0,
        age=45,
        city_pop=50_000,
        velocity=10,
        hour=23,
        day_of_week=2,
        geo_distance_km=80.0,
    )

    # 1) The flawed multi-feature LightGBM victim CLEARS it (score below threshold).
    target = LocalModelTarget(
        model_path=fraud_sparkov.MODEL_PATH,
        feature_names=fraud_sparkov.DETECTOR_FEATURES,
    )
    if not fraud_sparkov.MODEL_PATH.exists():
        pytest.skip("Sparkov flawed LightGBM artifact missing; run train.py")
    target_score = target.score(evasion)
    assert target_score < _THRESHOLD, target_score

    # 2) The cross-family IsolationForest DISAGREES: flags it as fraud.
    assert fraud_sparkov.isoforest_is_fraud(evasion) is True

    # 3) The differential oracle turns the disagreement into a FAIL vote.
    ctx = VerdictContext(
        sample=evasion,
        detector_score=target_score,
        threshold=_THRESHOLD,
        true_label=True,
        original_sample=None,
        original_score=None,
        spec=fraud_sparkov.load_spec(),
    )
    vote = DifferentialOracle(
        second_opinion_is_fraud=fraud_sparkov.isoforest_is_fraud
    ).vote(ctx)
    assert vote.kind is OracleKind.DIFFERENTIAL
    assert vote.vote is Vote.FAIL and vote.weight == 1.0
