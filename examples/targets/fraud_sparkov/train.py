"""Train the deployed VICTIM detector — realistic, multi-feature, but blind.

Part B1 rework: the victim is no longer a 2-feature (amt + cat_risk) toy. It is a
LightGBM trained on a believable SUBSET of the rich feature menu — the
static/contextual signals ``amt, cat_risk, merchant_risk, age, city_pop``
(``constants.DETECTOR_FEATURES``) — but deliberately BLIND to the
behavioral/temporal/geo signals ``velocity, day_of_week, geo_distance_km``
(``constants.BLIND_FEATURES``). This models a plausible real gap: "we never
engineered the behavioral features." The victim is decent on the natural
distribution (report its held-out AUC) yet flawed in WHICH signals it weighs, so
the strong reference model (which uses all of them) and the red loop can exploit
the missing behavioral axis.

Run as a module to (re)build the artifact:
    python -m examples.targets.fraud_sparkov.train
"""

from pathlib import Path

import joblib
import lightgbm as lgb
from lightgbm import Booster
from sklearn.metrics import roc_auc_score

from examples.targets.fraud_sparkov.constants import (
    BLIND_FEATURES,
    DETECTOR_FEATURES,
    MODEL_PATH,
    TEST_CSV,
    TRAIN_CSV,
)
from examples.targets.fraud_sparkov.loader import load_dataframe

_RANDOM_STATE = 42


def train_and_serialize(out_path: Path = MODEL_PATH) -> float:
    """Train on real data over DETECTOR_FEATURES, serialize, return test AUC."""
    train = load_dataframe(TRAIN_CSV, limit=None)
    test = load_dataframe(TEST_CSV, limit=None)

    x_train = train[list(DETECTOR_FEATURES)].to_numpy(dtype=float)
    y_train = train["is_fraud"].to_numpy()
    x_test = test[list(DETECTOR_FEATURES)].to_numpy(dtype=float)
    y_test = test["is_fraud"].to_numpy()

    clf = lgb.LGBMClassifier(
        n_estimators=200,
        num_leaves=31,
        learning_rate=0.05,
        scale_pos_weight=10,
        random_state=_RANDOM_STATE,
        n_jobs=1,
        verbose=-1,
        deterministic=True,
        force_col_wise=True,
    )
    clf.fit(x_train, y_train)

    # Serialize the bare LightGBM Booster, NOT the sklearn wrapper: LightGBM 4.5+
    # synthesizes feature names on the wrapper even when fit on a bare numpy
    # array, tripping sklearn's "X does not have valid feature names" warning on
    # every score through LGBMClassifier.predict_proba. The generic
    # LocalModelTarget feeds bare vectors and falls back to model.predict; for a
    # binary booster Booster.predict returns the positive-class probability
    # directly — identical numbers, no sklearn in the inference path, no warning.
    booster: Booster = clf.booster_
    proba = booster.predict(x_test)
    auc = float(roc_auc_score(y_test, proba))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(booster, out_path)
    return auc


def main() -> None:
    auc = train_and_serialize()
    print("Sparkov deployed VICTIM detector trained on REAL data.")
    print(f"  features: {list(DETECTOR_FEATURES)} (static/contextual signals)")
    print(f"  BLIND to: {list(BLIND_FEATURES)} (behavioral/temporal/geo gap)")
    print(f"  held-out test AUC: {auc:.4f} (decent, but missing behavioral signal)")
    print(f"  serialized to: {MODEL_PATH}")


if __name__ == "__main__":
    main()
