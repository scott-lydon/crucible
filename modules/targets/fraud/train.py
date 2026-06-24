"""Train the fraud LightGBM classifier on the real Kaggle credit-card dataset.

Reads `data/creditcard.csv` (fetched by scripts/fetch_fraud_dataset.py), trains
a LightGBM binary classifier, evaluates ROC-AUC on a stratified held-out split,
and writes the booster to `artifacts/fraud-v1.lgb` plus a metadata JSON. No
synthetic data: it refuses to run if the real dataset is absent.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import lightgbm as lgb
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from modules.targets.fraud.fraud_target import DEFAULT_ARTIFACT_PATH, DEFAULT_METADATA_PATH

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CSV_PATH = _REPO_ROOT / "data" / "creditcard.csv"
_LABEL = "Class"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def train(
    csv_path: Path = DEFAULT_CSV_PATH,
    artifact_path: Path = DEFAULT_ARTIFACT_PATH,
    metadata_path: Path = DEFAULT_METADATA_PATH,
    *,
    test_size: float = 0.2,
    seed: int = 42,
) -> dict[str, Any]:
    """Train and persist the fraud model; return its metadata (including AUC)."""
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Fraud dataset not found at {csv_path}. Run scripts/fetch_fraud_dataset.py first."
        )
    frame = pd.read_csv(csv_path)
    if _LABEL not in frame.columns:
        raise ValueError(
            f"Expected a {_LABEL!r} column in {csv_path}; got {list(frame.columns)}."
        )

    features = [column for column in frame.columns if column != _LABEL]
    inputs = frame[features]
    labels = frame[_LABEL]
    train_x, holdout_x, train_y, holdout_y = train_test_split(
        inputs, labels, test_size=test_size, stratify=labels, random_state=seed
    )

    model = lgb.LGBMClassifier(
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=64,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=seed,
        n_jobs=-1,
        verbose=-1,
    )
    model.fit(train_x, train_y)
    holdout_proba = model.predict_proba(holdout_x)[:, 1]
    auc = float(roc_auc_score(holdout_y, holdout_proba))

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    model.booster_.save_model(str(artifact_path))
    metadata: dict[str, Any] = {
        "model": "lightgbm",
        "version": 1,
        "auc": auc,
        "trained_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": _sha256(csv_path),
        "features": features,
        "rows": int(len(frame)),
        "frauds": int(labels.sum()),
        "test_size": test_size,
        "seed": seed,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main() -> None:
    metadata = train()
    print(
        json.dumps(
            {
                "auc": metadata["auc"],
                "rows": metadata["rows"],
                "frauds": metadata["frauds"],
                "artifact": str(DEFAULT_ARTIFACT_PATH),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
