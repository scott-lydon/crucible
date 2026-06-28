"""Retrainer (PR3 port C1).

The middle step of the fraud hardening loop: retrain the LightGBM classifier with the
proposed adversarial samples upweighted, and write the new versioned model artifact. Kept
separate from proposal and held-out validation so the retrain is independently auditable.
Self-contained LightGBM (imports shared data + lightgbm, never modules.targets) so the
module-import rule holds.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np

from shared.datasets.fraud import load_splits

ARTIFACTS = Path(__file__).resolve().parents[2] / "artifacts"
THRESHOLD = 0.5
_UPWEIGHT = 50


@dataclass(frozen=True, slots=True)
class Retrainer:
    """Retrains fraud-v{n+1} from fraud-v{n} plus the upweighted adversarial samples."""

    upweight: int = _UPWEIGHT

    def retrain(
        self, features: list[str], adv: Sequence[Mapping[str, Any]], new_version: int
    ) -> str:
        """Train and persist the new model version; return its version label."""
        splits = load_splits()
        x_train = splits.x_train.to_numpy()
        y_train = splits.y_train.to_numpy()
        if adv:
            x_adv = np.asarray([[float(r.get(f, 0.0)) for f in features] for r in adv])
            x_train = np.vstack([x_train, np.repeat(x_adv, self.upweight, axis=0)])
            y_train = np.concatenate(
                [y_train, np.ones(x_adv.shape[0] * self.upweight, dtype=int)]
            )
        spw = float((y_train == 0).sum()) / max(int((y_train == 1).sum()), 1)
        clf = lgb.LGBMClassifier(
            n_estimators=200, learning_rate=0.05, num_leaves=31,
            scale_pos_weight=spw, random_state=42, n_jobs=2, verbose=-1,
        )
        clf.fit(x_train, y_train)
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        clf.booster_.save_model(str(ARTIFACTS / f"fraud-v{new_version}.lgb"))
        meta = {
            "version": new_version, "feature_names": features, "threshold": THRESHOLD,
            "trained_at": dt.datetime.now(dt.UTC).isoformat(),
            "blue_retrain": True, "adversarial_samples": len(adv),
        }
        (ARTIFACTS / f"fraud-v{new_version}.meta.json").write_text(json.dumps(meta, indent=2))
        return f"fraud-v{new_version}"
