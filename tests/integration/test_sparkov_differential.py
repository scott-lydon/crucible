"""REAL cross-family disagreement on the Sparkov victim.

Proves the differential oracle's second opinion is genuine: an unsupervised
sklearn IsolationForest (a different model family) trained on the REAL Sparkov
data flags a night-hour, low-amount fraud that the amount-reliant LightGBM
target CLEARS. That disagreement is exactly what the differential oracle turns
into a FAIL vote — a real cross-family catch, nothing mocked.

Skips (rather than fails) when the external CSVs are absent — they are
gitignored inputs, not source. The IsolationForest artifact is built on demand
if missing (deterministic, seeded), so the test is self-contained and fast.
"""

import pytest

from examples.targets import fraud_sparkov
from examples.targets.fraud_sparkov import second_model
from examples.targets.fraud_sparkov.constants import NIGHT_HOURS
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
_NIGHT_HOUR = next(iter(NIGHT_HOURS))


@pytest.fixture(scope="module")
def _ensure_isoforest() -> None:
    if not second_model.SECOND_MODEL_PATH.exists():
        second_model.train_and_serialize()


@pytest.mark.skipif(not _DATA_READY, reason=_SKIP_REASON)
def test_isoforest_flags_night_evasion_lightgbm_clears(_ensure_isoforest: None) -> None:
    # A night-hour, low-amount, non-risky-category transaction: the declared
    # rule labels it fraud (night hour), the amt-reliant LightGBM clears it
    # (low amt), and the cross-family IsolationForest flags it as anomalous.
    evasion = SparkovTxn(
        txn_index=0, amt=12.0, cat_risk=0, hour=_NIGHT_HOUR, age=45, city_pop=50_000
    )

    # 1) The declared ground truth: this IS fraud.
    assert fraud_sparkov.is_fraud(evasion) is True

    # 2) The flawed LightGBM target CLEARS it (score below threshold).
    target = LocalModelTarget(
        model_path=fraud_sparkov.MODEL_PATH,
        feature_names=fraud_sparkov.DETECTOR_FEATURES,
    )
    if not fraud_sparkov.MODEL_PATH.exists():
        pytest.skip("Sparkov flawed LightGBM artifact missing; run train.py")
    target_score = target.score(evasion)
    assert target_score < _THRESHOLD, target_score

    # 3) The cross-family IsolationForest DISAGREES: flags it as fraud.
    assert fraud_sparkov.isoforest_is_fraud(evasion) is True

    # 4) The differential oracle turns the disagreement into a FAIL vote.
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
