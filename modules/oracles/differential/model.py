"""The differential second implementation for the fraud target: a scikit-learn
IsolationForest. A different model family from the LightGBM producer (isolation trees
vs gradient boosting), so it fails differently — the point of the differential oracle
(plan.md section 5). It ranks fraud well (held-out AUC ~0.94); the decision is the
anomaly score against a threshold calibrated at the 98th percentile of training
scores (NOT IsolationForest.predict, whose fixed contamination is far too strict).

No LLM — this oracle is token-free."""

from __future__ import annotations

import datetime as dt
import json
import pickle
from pathlib import Path
from typing import Any, cast

import numpy as np
from sklearn.ensemble import IsolationForest

from shared.datasets.fraud import load_splits

ARTIFACTS = Path(__file__).resolve().parents[3] / "artifacts"
SCORE_PERCENTILE = 98.0


def iso_path(version: int) -> Path:
    return ARTIFACTS / f"fraud-iso-v{version}.pkl"


def iso_meta_path(version: int) -> Path:
    return ARTIFACTS / f"fraud-iso-v{version}.meta.json"


def train_isoforest(version: int = 1) -> dict[str, Any]:
    splits = load_splits()
    x_train = splits.x_train.to_numpy()
    model = IsolationForest(n_estimators=200, contamination="auto", random_state=42, n_jobs=2)
    model.fit(x_train)
    # Higher anomaly score = more fraud-like. Threshold at the 98th training percentile.
    train_scores = -cast("Any", model.decision_function(x_train))
    threshold = float(np.percentile(train_scores, SCORE_PERCENTILE))

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload = {"model": model, "features": splits.feature_names, "threshold": threshold}
    iso_path(version).write_bytes(pickle.dumps(payload))
    meta: dict[str, Any] = {
        "version": version,
        "family": "IsolationForest",
        "n_estimators": 200,
        "anomaly_threshold": threshold,
        "score_percentile": SCORE_PERCENTILE,
        "feature_names": splits.feature_names,
        "trained_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    iso_meta_path(version).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def ensure_isoforest(version: int = 1) -> dict[str, Any]:
    if iso_path(version).exists() and iso_meta_path(version).exists():
        raw = iso_meta_path(version).read_text(encoding="utf-8")
        meta = cast("dict[str, Any]", json.loads(raw))
        if "anomaly_threshold" in meta:   # older artifact lacks the calibrated threshold
            return meta
    return train_isoforest(version)


def load_isoforest(version: int = 1) -> tuple[IsolationForest, list[str], float]:
    if not iso_path(version).exists():
        raise FileNotFoundError(f"fraud-iso-v{version} not trained. Run ensure_isoforest().")
    payload = cast("dict[str, Any]", pickle.loads(iso_path(version).read_bytes()))
    return payload["model"], list(payload["features"]), float(payload["threshold"])
