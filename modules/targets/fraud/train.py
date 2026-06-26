"""Train the fraud LightGBM classifier on real data and serialize it under
``artifacts/fraud-vN.lgb`` with a sidecar metadata JSON. This is the Shape-1 "retrain"
operation (docs/VOCABULARY.md): a bounded single-machine ``LGBMClassifier.fit`` pass,
not LLM fine-tuning.

``ensure_model`` is idempotent so tests and the container can call it cheaply; the
artifact is gitignored and regenerated, never committed (constitution.md section 5)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import lightgbm as lgb
from sklearn.metrics import roc_auc_score

from shared.datasets.fraud import load_splits

ARTIFACTS = Path(__file__).resolve().parents[3] / "artifacts"
DEFAULT_THRESHOLD = 0.5


def model_path(version: int) -> Path:
    return ARTIFACTS / f"fraud-v{version}.lgb"


def meta_path(version: int) -> Path:
    return ARTIFACTS / f"fraud-v{version}.meta.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def train_and_save(
    version: int = 1, *, extra_samples: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Train and serialize fraud-vN. ``extra_samples`` (adversarial training rows from
    the blue loop, slice 14) are appended to the real training data when present."""
    splits = load_splits()
    x_train, y_train = splits.x_train, splits.y_train

    if extra_samples:
        import pandas as pd  # local: only the blue retrain path needs it

        extra_df = pd.DataFrame(extra_samples)[splits.feature_names]
        extra_y = pd.Series([1] * len(extra_df))  # adversarial samples are labelled fraud
        x_train = pd.concat([x_train, extra_df], ignore_index=True)
        y_train = pd.concat([y_train, extra_y], ignore_index=True)

    n_pos = int((y_train == 1).sum())
    n_neg = int((y_train == 0).sum())
    scale_pos_weight = (n_neg / n_pos) if n_pos else 1.0

    clf = lgb.LGBMClassifier(
        n_estimators=200, learning_rate=0.05, num_leaves=31,
        scale_pos_weight=scale_pos_weight, random_state=42, n_jobs=2, verbose=-1,
    )
    clf.fit(x_train, y_train)

    eval_proba = clf.predict_proba(splits.x_eval)[:, 1]
    auc = float(roc_auc_score(splits.y_eval, eval_proba))

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    booster = clf.booster_
    booster.save_model(str(model_path(version)))

    meta: dict[str, Any] = {
        "version": version,
        "feature_names": splits.feature_names,
        "threshold": DEFAULT_THRESHOLD,
        "auc_eval": auc,
        "n_train": len(x_train),
        "n_eval": len(splits.x_eval),
        "scale_pos_weight": scale_pos_weight,
        "data_sha256": splits.data_sha256,
        "model_sha256": _sha256_file(model_path(version)),
        "trained_at": dt.datetime.now(dt.UTC).isoformat(),
        "extra_samples": len(extra_samples or []),
    }
    meta_path(version).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def ensure_model(version: int = 1) -> dict[str, Any]:
    """Return metadata for fraud-vN, training it first only if missing."""
    if model_path(version).exists() and meta_path(version).exists():
        return cast("dict[str, Any]", json.loads(meta_path(version).read_text(encoding="utf-8")))
    return train_and_save(version)


if __name__ == "__main__":
    info = train_and_save(1)
    print(json.dumps(info, indent=2))
