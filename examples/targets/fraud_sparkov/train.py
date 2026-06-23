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

    # Fit on bare numpy arrays (no DataFrame feature names) so the serialized
    # model scores plain feature vectors from LocalModelTarget without emitting
    # "X does not have valid feature names" warnings at inference time.
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

    proba = clf.predict_proba(x_test)[:, 1]
    auc = float(roc_auc_score(y_test, proba))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, out_path)
    return auc


def main() -> None:
    auc = train_and_serialize()
    print("Sparkov flawed detector trained on REAL data.")
    print(f"  features: {list(DETECTOR_FEATURES)} (deliberately amt-reliant)")
    print(f"  held-out test AUC: {auc:.4f}")
    print(f"  serialized to: {MODEL_PATH}")


if __name__ == "__main__":
    main()
