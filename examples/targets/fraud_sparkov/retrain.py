"""Victim retraining capability — the blue loop's INJECTED hardening hook.

This is victim-specific knowledge that lives in the Sparkov example, never in the
harness. The blue pillar (``modules/blue/``) is target-agnostic; it calls back
into THIS function (injected as ``retrain_fn``) to produce a hardened detector.

``retrain_with_features`` trains a NEW LightGBM on the REAL fraudTrain.csv over a
caller-supplied feature set, so passing ``["amt", "cat_risk", "hour", "distance"]``
yields a model that uses the previously-blind ``hour``/``distance`` the current
flawed detector ignores. The fit is deterministic (seeded), the dataset checksum
is verified before training (external-input guard), and the artifact is written
to ``artifacts/sparkov_blue_<hash>.lgb`` (gitignored). It returns the path so the
generic ``LocalModelTarget`` can load the new model over the SAME feature order.

``AVAILABLE_FEATURES`` is everything the victim CAN train on (the strong night
``hour`` and the noise ``distance`` included). ``CURRENT_FEATURES`` mirrors the
deployed flawed detector's narrow proxy set (``amt``, ``cat_risk``) — the blind
spot the red loop exploits and the blue loop closes.
"""

import hashlib
from collections.abc import Sequence
from pathlib import Path

import joblib
import lightgbm as lgb
from lightgbm import Booster

from examples.targets.fraud_sparkov.constants import (
    DETECTOR_FEATURES,
    TRAIN_CSV,
)
from examples.targets.fraud_sparkov.loader import load_dataframe, verify_checksum

_RANDOM_STATE = 42
_HERE: Path = Path(__file__).resolve().parent
_ARTIFACTS: Path = _HERE / "artifacts"

# Everything the victim CAN train on. ``distance`` is the Step-1 noise feature
# (fraud/legit share an identical distribution); ``hour`` is the dominant night
# signal the deployed detector ignores. Both are exposed so the blue proposer
# can reason over the full menu and the retrainer can honestly add them.
AVAILABLE_FEATURES: tuple[str, ...] = ("amt", "cat_risk", "hour", "distance", "age", "city_pop")

# The deployed flawed detector's feature set (single point of truth: the victim
# constants). The blind spot is everything in AVAILABLE_FEATURES not in here.
CURRENT_FEATURES: tuple[str, ...] = tuple(DETECTOR_FEATURES)


def _features_hash(feature_names: Sequence[str]) -> str:
    """Stable short hash of the ordered feature set, for the artifact filename."""
    joined = ",".join(feature_names)
    return hashlib.sha256(joined.encode()).hexdigest()[:12]


def retrain_with_features(
    feature_names: Sequence[str], seed: int = _RANDOM_STATE
) -> Path:
    """Train a NEW LightGBM on the REAL Sparkov data over ``feature_names``.

    Verifies the dataset checksum, fits deterministically, serializes the bare
    Booster to ``artifacts/sparkov_blue_<hash>.lgb`` (gitignored), and returns
    the path. The feature ORDER is preserved so the generic ``LocalModelTarget``
    can score samples by feeding ``getattr(sample, name)`` in the same order.
    """
    features = list(feature_names)
    if not features:
        raise ValueError("retrain_with_features: feature_names must be non-empty.")
    unknown = [f for f in features if f not in AVAILABLE_FEATURES]
    if unknown:
        raise ValueError(
            f"retrain_with_features: unknown features {unknown}; "
            f"the victim can only train on {list(AVAILABLE_FEATURES)}."
        )

    verify_checksum(TRAIN_CSV)
    train = load_dataframe(TRAIN_CSV, limit=None)
    x_train = train[features].to_numpy(dtype=float)
    y_train = train["is_fraud"].to_numpy()

    clf = lgb.LGBMClassifier(
        n_estimators=200,
        num_leaves=15,
        learning_rate=0.05,
        scale_pos_weight=10,
        random_state=seed,
        n_jobs=1,
        verbose=-1,
        deterministic=True,
        force_col_wise=True,
    )
    clf.fit(x_train, y_train)
    booster: Booster = clf.booster_

    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out_path = _ARTIFACTS / f"sparkov_blue_{_features_hash(features)}.lgb"
    joblib.dump(booster, out_path)
    return out_path
