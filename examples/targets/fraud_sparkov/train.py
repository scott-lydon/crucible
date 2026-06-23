"""Train the deliberately proxy-reliant flawed Sparkov detector.

The detector is a LightGBM classifier fit on the REAL fraudTrain.csv using ONLY
the ``amt`` + ``cat_risk`` proxies. It deliberately ignores the strongest causal
signal (night hour) and the noise feature (distance), so it stays accurate on
the natural distribution (AUC ~0.97) yet is blind to amt-lowering on
night-driven frauds — the exploitable gap the red loop attacks.

Run as a module to (re)build the artifact:
    python -m examples.targets.fraud_sparkov.train
"""

from pathlib import Path

import joblib
import lightgbm as lgb
from lightgbm import Booster
from sklearn.metrics import roc_auc_score

from examples.targets.fraud_sparkov.constants import (
    DETECTOR_FEATURES,
    MODEL_PATH,
    TEST_CSV,
    TRAIN_CSV,
)
from examples.targets.fraud_sparkov.loader import load_dataframe

_RANDOM_STATE = 42


def train_and_serialize(out_path: Path = MODEL_PATH) -> float:
    """Train on real data, serialize the model, return held-out test AUC."""
    train = load_dataframe(TRAIN_CSV, limit=None)
    test = load_dataframe(TEST_CSV, limit=None)

    x_train = train[list(DETECTOR_FEATURES)].to_numpy()
    y_train = train["is_fraud"].to_numpy()
    x_test = test[list(DETECTOR_FEATURES)].to_numpy()
    y_test = test["is_fraud"].to_numpy()

    clf = lgb.LGBMClassifier(
        n_estimators=200,
        num_leaves=15,
        learning_rate=0.05,
        scale_pos_weight=10,
        random_state=_RANDOM_STATE,
        n_jobs=1,
        verbose=-1,
        deterministic=True,
        force_col_wise=True,
    )
    clf.fit(x_train, y_train)

    # Serialize the bare LightGBM Booster, NOT the sklearn LGBMClassifier wrapper.
    # LightGBM 4.5+ synthesizes feature names ("Column_0", ...) on the wrapper
    # even when fit on a bare numpy array, so scoring an unnamed array through
    # LGBMClassifier.predict_proba trips sklearn's "X does not have valid feature
    # names" UserWarning on every call. The generic LocalModelTarget feeds bare
    # vectors and falls back to `model.predict([vec])` when there is no
    # `predict_proba`; for a binary booster `Booster.predict` returns the
    # positive-class probability directly — identical numbers, no sklearn in the
    # inference path, no warning. Keeps the adapter fully generic.
    booster: Booster = clf.booster_
    proba = booster.predict(x_test)
    auc = float(roc_auc_score(y_test, proba))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(booster, out_path)
    return auc


def main() -> None:
    auc = train_and_serialize()
    print("Sparkov flawed detector trained on REAL data.")
    print(f"  features: {list(DETECTOR_FEATURES)} (deliberately amt-reliant)")
    print(f"  held-out test AUC: {auc:.4f}")
    print(f"  serialized to: {MODEL_PATH}")


if __name__ == "__main__":
    main()
