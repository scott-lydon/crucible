"""Strong REFERENCE model — the best-available ground-truth PROXY.

This REPLACES the old night-hour ``rule.py`` ``is_fraud`` as the oracle's ground
truth. Where that rule was a hand-written 2-clause heuristic (high recall, ~2%
precision), this is a LightGBM trained on the FULL rich feature set
(``constants.RICH_FEATURES``) against the REAL ``is_fraud`` labels (train split).
Because it weighs MANY real signals — amount, per-merchant risk, demographics,
and the behavioral/temporal/geo signals the deployed victim lacks — it judges
ANY transaction (including red-mutated ones) credibly: the label it assigns is a
strong, calibrated prediction, not a single-feature tripwire.

HONEST FRAMING: this is a PROXY for ground truth, not infallible truth. We report
its held-out test AUC so its quality is auditable. ``reference_is_fraud`` is the
operating-point decision (predict_proba > ``REFERENCE_THRESHOLD``); it can be
wrong on individual transactions just like any model. It is, however, a far more
honest and multi-signal ground truth than the retired night-hour rule.

Build the artifact:
    python -m examples.targets.fraud_sparkov.reference_model
"""

from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
from lightgbm import Booster
from sklearn.metrics import roc_auc_score

from examples.targets.fraud_sparkov.constants import (
    REFERENCE_MODEL_PATH,
    REFERENCE_THRESHOLD,
    RICH_FEATURES,
    TEST_CSV,
    TRAIN_CSV,
)
from examples.targets.fraud_sparkov.loader import load_dataframe, verify_checksum
from examples.targets.fraud_sparkov.record import SparkovTxn

_RANDOM_STATE = 42

# Cache the loaded booster across scoring calls within a process.
_MODEL: Booster | None = None


def _vector(sample: object) -> list[float]:
    """Build the reference feature vector off an opaque ``SparkovTxn``."""
    if not isinstance(sample, SparkovTxn):  # defensive: harness passes SparkovTxn
        raise TypeError(
            f"reference_model: expected SparkovTxn sample, got {type(sample).__name__}"
        )
    return [float(getattr(sample, name)) for name in RICH_FEATURES]


def train_and_serialize(out_path: Path = REFERENCE_MODEL_PATH) -> float:
    """Train the reference model on the full rich set + real labels; return AUC.

    Verifies both dataset checksums (external-input guard), fits deterministically
    on the train split over ``RICH_FEATURES``, evaluates AUC on the held-out test
    split, serializes the bare Booster (gitignored artifact), and returns the AUC.
    """
    verify_checksum(TRAIN_CSV)
    verify_checksum(TEST_CSV)
    train = load_dataframe(TRAIN_CSV, limit=None)
    test = load_dataframe(TEST_CSV, limit=None)

    x_train = train[list(RICH_FEATURES)].to_numpy(dtype=float)
    y_train = train["is_fraud"].to_numpy()
    x_test = test[list(RICH_FEATURES)].to_numpy(dtype=float)
    y_test = test["is_fraud"].to_numpy()

    clf = lgb.LGBMClassifier(
        n_estimators=400,
        num_leaves=63,
        learning_rate=0.05,
        scale_pos_weight=10,
        random_state=_RANDOM_STATE,
        n_jobs=1,
        verbose=-1,
        deterministic=True,
        force_col_wise=True,
    )
    clf.fit(x_train, y_train)

    booster: Booster = clf.booster_
    proba = booster.predict(x_test)
    auc = float(roc_auc_score(y_test, proba))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(booster, out_path)
    return auc


def _load_model() -> Booster:
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    if not REFERENCE_MODEL_PATH.exists():
        raise FileNotFoundError(
            f"reference_model: artifact not found at '{REFERENCE_MODEL_PATH}'. "
            "It is a gitignored external input; build it with "
            "`python -m examples.targets.fraud_sparkov.reference_model`."
        )
    model: Booster = joblib.load(REFERENCE_MODEL_PATH)
    _MODEL = model
    return model


def reference_is_fraud(sample: object) -> bool:
    """Ground-truth PROXY label: is ``sample`` fraud per the reference model?

    Loads the serialized reference booster (cached) and returns ``True`` when its
    predicted fraud probability exceeds ``REFERENCE_THRESHOLD``. This is the
    oracle ``label_fn`` — it judges any transaction (incl. red-mutated) on many
    signals, not a single-feature rule.
    """
    model = _load_model()
    vec = np.asarray([_vector(sample)], dtype=float)
    proba = float(model.predict(vec)[0])
    return proba > REFERENCE_THRESHOLD


def main() -> None:
    auc = train_and_serialize()
    print("Sparkov REFERENCE model (ground-truth proxy) trained on REAL data.")
    print(f"  features: {list(RICH_FEATURES)} (full rich set)")
    print(f"  held-out test AUC: {auc:.4f}")
    print(f"  decision threshold: {REFERENCE_THRESHOLD} (predict_proba >)")
    print(f"  serialized to: {REFERENCE_MODEL_PATH}")
    print(
        "  NOTE: best-available ground-truth PROXY (report AUC, not infallible)."
    )


if __name__ == "__main__":
    main()
