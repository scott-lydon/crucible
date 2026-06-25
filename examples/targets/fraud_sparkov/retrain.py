"""Victim retraining capability — the blue loop's INJECTED hardening hook.

This is victim-specific knowledge that lives in the Sparkov example, never in the
harness. The blue pillar (``modules/blue/``) is target-agnostic; it calls back
into THIS function (injected as ``retrain_fn``) to produce a hardened detector.

``retrain_with_features`` trains a NEW LightGBM on the REAL fraudTrain.csv over a
caller-supplied feature set, so passing the deployed feature set PLUS a blind
behavioral signal (e.g. ``"velocity"`` or ``"hour"``) yields a model that uses a
signal the current victim ignores. The fit is deterministic (seeded), the dataset
checksum is verified before training (external-input guard), and the artifact is
written to ``artifacts/sparkov_blue_<hash>.lgb`` (gitignored). It returns the path
so the generic ``LocalModelTarget`` can load the new model over the SAME feature
order.

``AVAILABLE_FEATURES`` is everything the victim CAN train on — the full rich menu
(``constants.RICH_FEATURES``), including the behavioral/temporal/geo signals the
deployed detector lacks. ``CURRENT_FEATURES`` mirrors the deployed victim's
static/contextual set (``constants.DETECTOR_FEATURES``) — the blind set
(``constants.BLIND_FEATURES``) is exactly the gap the red loop exploits and the
blue loop closes.
"""

import hashlib
from collections.abc import Sequence
from pathlib import Path

import joblib
import lightgbm as lgb
from lightgbm import Booster

from examples.targets.fraud_sparkov.constants import (
    DETECTOR_FEATURES,
    RICH_FEATURES,
    TRAIN_CSV,
)
from examples.targets.fraud_sparkov.loader import load_dataframe, verify_checksum

_RANDOM_STATE = 42
_HERE: Path = Path(__file__).resolve().parent
_ARTIFACTS: Path = _HERE / "artifacts"

# Everything the victim CAN train on: the full rich menu, including the behavioral
# (velocity), temporal (hour, day_of_week), and geo (geo_distance_km) signals the
# deployed detector ignores. Exposed so the blue proposer can reason over the full
# menu and the retrainer can honestly add the blind signals back.
AVAILABLE_FEATURES: tuple[str, ...] = tuple(RICH_FEATURES)

# The deployed victim's feature set (single point of truth: the victim constants).
# The blind set is everything in AVAILABLE_FEATURES not in here.
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
