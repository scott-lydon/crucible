"""Retrainer: apply a blue patch to the target (ARCHITECTURE.md Pillar 3).

For the fraud target it runs a LightGBM training pass that folds the patch's
adversarial samples (real frauds the current model missed) into the training set
and emits a new ``artifacts/fraud-vN.lgb`` at the next version integer. For the
code-agent target it turns the patch into a new agent prompt-and-configuration at
the next version integer; the vendor language model the code agent talks to is
never modified. It runs no LLM itself: the proposal already chose the strategy,
the retrainer only executes it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from modules.blue.errors import RetrainFailed
from shared.types import BluePatch


def fraud_scorer(artifact_path: Path) -> Callable[[dict[str, Any]], Awaitable[float]]:
    """Return an async score function for a saved fraud booster.

    Loads the booster directly (lightgbm is a library, not a sibling module) and
    aligns each payload to the model's own feature order, so the held-out
    validator can score the old and the new model with the same code path without
    importing the fraud target module.
    """
    booster = lgb.Booster(model_file=str(artifact_path))
    features = list(booster.feature_name())

    async def score(payload: dict[str, Any]) -> float:
        row = np.asarray([feature_row(payload, features)], dtype=float)
        return float(booster.predict(row)[0])

    return score


def feature_row(attack_input: dict[str, Any], features: list[str]) -> list[float]:
    """Build the model's feature vector from a transaction dict, in train order.

    Inlined rather than imported from modules.targets.fraud: the module-boundary
    rule forbids a cross-module import, and this is the same alignment (absent,
    null, or non-numeric feature defaults to 0.0, present numeric values coerced
    to float).
    """
    row: list[float] = []
    for name in features:
        value = attack_input.get(name)
        row.append(float(value) if isinstance(value, (int, float)) else 0.0)
    return row

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACTS_DIR = _REPO_ROOT / "artifacts"
DEFAULT_CSV_PATH = _REPO_ROOT / "data" / "creditcard.csv"
DEFAULT_METADATA_PATH = _REPO_ROOT / "artifacts" / "fraud-v1.meta.json"
_LABEL = "Class"
_VERSION_RE = re.compile(r"fraud-v(\d+)\.lgb$")


@dataclass(frozen=True, slots=True)
class RetrainResult:
    """The outcome of a fraud retrain: the new artifact and its provenance."""

    version: int
    artifact_path: Path
    auc: float
    train_rows: int
    adversarial_added: int

    def as_metrics(self) -> dict[str, Any]:
        return {
            "auc": self.auc,
            "train_rows": self.train_rows,
            "adversarial_added": self.adversarial_added,
        }


@dataclass(frozen=True, slots=True)
class CodeConfigResult:
    """The outcome of a code-agent patch: a new prompt-and-config version."""

    version: int
    system_prompt: str
    config: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Retrainer:
    """Executes a blue patch into a new target version. No LLM."""

    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR
    csv_path: Path = DEFAULT_CSV_PATH
    metadata_path: Path = DEFAULT_METADATA_PATH
    adversarial_weight: int = 50

    def next_fraud_version(self) -> int:
        """The next fraud artifact version integer (one past the highest on disk)."""
        versions = [
            int(m.group(1))
            for p in self.artifacts_dir.glob("fraud-v*.lgb")
            if (m := _VERSION_RE.search(p.name))
        ]
        return (max(versions) + 1) if versions else 1

    def retrain_fraud(self, patch: BluePatch, *, seed: int = 42) -> RetrainResult:
        """Retrain LightGBM with the patch's adversarial samples folded in.

        The adversarial samples are real frauds the prior model missed; they are
        labeled fraud and oversampled so the new model fits the missed region,
        then a fresh booster is trained and saved at the next version integer.
        """
        if not self.csv_path.exists():
            raise RetrainFailed(
                f"cannot retrain fraud-v{self.next_fraud_version()}: dataset missing at "
                f"{self.csv_path}. Run scripts/fetch_fraud_dataset.py first."
            )
        version = self.next_fraud_version()
        try:
            return self._retrain_fraud(patch, version, seed)
        except RetrainFailed:
            raise
        except Exception as exc:  # one sanctioned wrap: name the version being written
            raise RetrainFailed(
                f"retrain of fraud-v{version} failed: {type(exc).__name__}: {exc}"
            ) from exc

    def _retrain_fraud(self, patch: BluePatch, version: int, seed: int) -> RetrainResult:
        frame = pd.read_csv(self.csv_path)
        features = [c for c in frame.columns if c != _LABEL]

        samples = patch.detail.get("adversarial_samples", [])
        adversarial = self._adversarial_frame(samples, features)
        train_frame = pd.concat([frame, adversarial], ignore_index=True) if len(
            adversarial
        ) else frame

        inputs = train_frame[features]
        labels = train_frame[_LABEL]
        train_x, holdout_x, train_y, holdout_y = train_test_split(
            inputs, labels, test_size=0.2, stratify=labels, random_state=seed
        )
        config = patch.detail.get("train_config", {})
        model = lgb.LGBMClassifier(
            n_estimators=int(config.get("n_estimators", 400)),
            learning_rate=float(config.get("learning_rate", 0.05)),
            num_leaves=int(config.get("num_leaves", 64)),
            scale_pos_weight=float(config.get("scale_pos_weight", 1.0)),
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=seed,
            n_jobs=-1,
            verbose=-1,
        )
        model.fit(train_x, train_y)
        auc = float(roc_auc_score(holdout_y, model.predict_proba(holdout_x)[:, 1]))

        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = self.artifacts_dir / f"fraud-v{version}.lgb"
        model.booster_.save_model(str(artifact_path))
        self._write_meta(version, features, auc, artifact_path)
        return RetrainResult(
            version=version,
            artifact_path=artifact_path,
            auc=auc,
            train_rows=int(len(train_frame)),
            adversarial_added=len(samples),
        )

    def _adversarial_frame(
        self, samples: list[dict[str, Any]], features: list[str]
    ) -> pd.DataFrame:
        """Build oversampled fraud-labeled rows from the patch's missed-fraud samples."""
        if not samples:
            return pd.DataFrame(columns=[*features, _LABEL])
        rows = []
        for sample in samples:
            row = dict(zip(features, feature_row(sample, features), strict=True))
            row[_LABEL] = 1
            rows.extend([row] * self.adversarial_weight)
        return pd.DataFrame(rows)

    def _write_meta(
        self, version: int, features: list[str], auc: float, artifact_path: Path
    ) -> None:
        meta = {
            "model": "lightgbm",
            "version": version,
            "auc": auc,
            "trained_at": datetime.now(UTC).isoformat(),
            "features": features,
            "hardened": True,
        }
        artifact_path.with_suffix(".meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )

    def apply_code_config(self, patch: BluePatch, *, version: int) -> CodeConfigResult:
        """Turn a prompt_config patch into a new agent prompt-and-config version.

        The caller persists the agent_configs row; this only assembles the new
        version from the patch (the vendor model is never touched).
        """
        detail = patch.detail
        system_prompt = str(detail.get("system_prompt_additions", "")).strip()
        config = detail.get("config", {})
        return CodeConfigResult(
            version=version,
            system_prompt=system_prompt,
            config=config if isinstance(config, dict) else {},
        )
