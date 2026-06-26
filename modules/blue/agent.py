"""FraudBlueAgent: the Shape-1 hardening loop (spec US-7, plan.md section 3 Pillar 3).
Reads the strategy catalog (the undetected-hack attacks), retrains the LightGBM
classifier with those adversarial samples, and validates detection on a held-out
attack set DEFINED UP FRONT that the retrain never touches (the held-out firewall,
constitution.md section 3).

Self-contained LightGBM (imports shared data + lightgbm, never modules.targets) so the
module-import rule holds. It reports the true before/after recall and NEVER fakes a
recovery: on the production fraud model the residual misses are idiosyncratic and do
not generalize (the "blue overfits / does not converge" residual, plan.md section 6),
so ``validated`` is honest."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import lightgbm as lgb
import numpy as np

from shared.datasets.fraud import load_splits
from shared.types.core import Attack, AuditTrace
from shared.types.enums import Pillar
from shared.types.ids import RunId, new_id
from shared.types.results import HealthStatus, PatchResult
from shared.types.sealed_spec import SealedSpec

ARTIFACTS = Path(__file__).resolve().parents[2] / "artifacts"
THRESHOLD = 0.5
_UPWEIGHT = 50


class FraudBlueAgent:
    def __init__(self, base_version: int = 1) -> None:
        self._base = base_version

    def _booster(self, version: int) -> lgb.Booster:
        return lgb.Booster(model_file=str(ARTIFACTS / f"fraud-v{version}.lgb"))

    def _recall(self, booster: lgb.Booster, features: list[str],
                rows: Sequence[Mapping[str, Any]]) -> float:
        if not rows:
            return 0.0
        x = np.asarray([[float(r.get(f, 0.0)) for f in features] for r in rows])
        preds = np.asarray(cast("Any", booster.predict(x)))
        return float(np.sum(preds >= THRESHOLD)) / len(rows)

    def _retrain(self, features: list[str], adv: Sequence[Mapping[str, Any]], version: int) -> None:
        splits = load_splits()
        x_train = splits.x_train.to_numpy()
        y_train = splits.y_train.to_numpy()
        if adv:
            x_adv = np.asarray([[float(r.get(f, 0.0)) for f in features] for r in adv])
            x_train = np.vstack([x_train, np.repeat(x_adv, _UPWEIGHT, axis=0)])
            y_train = np.concatenate([y_train, np.ones(x_adv.shape[0] * _UPWEIGHT, dtype=int)])
        spw = float((y_train == 0).sum()) / max(int((y_train == 1).sum()), 1)
        clf = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, num_leaves=31,
                                 scale_pos_weight=spw, random_state=42, n_jobs=2, verbose=-1)
        clf.fit(x_train, y_train)
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        clf.booster_.save_model(str(ARTIFACTS / f"fraud-v{version}.lgb"))
        meta = {"version": version, "feature_names": features, "threshold": THRESHOLD,
                "trained_at": dt.datetime.now(dt.UTC).isoformat(),
                "blue_retrain": True, "adversarial_samples": len(adv)}
        (ARTIFACTS / f"fraud-v{version}.meta.json").write_text(json.dumps(meta, indent=2))

    async def harden(
        self, spec: SealedSpec, run_id: RunId, catalog_slice: Sequence[Attack]
    ) -> PatchResult:
        splits = load_splits()
        features = list(splits.feature_names)
        adv = [{k: float(v) for k, v in a.payload.items()} for a in catalog_slice]
        # Held-out validation attacks: eval-split frauds, fixed up front, disjoint from the
        # adversarial samples (which come from the holdout split).
        validation = [
            {k: float(v) for k, v in splits.x_eval.loc[i].to_dict().items()}
            for i in splits.y_eval[splits.y_eval == 1].index
        ]
        before = self._recall(self._booster(self._base), features, validation)
        new_version = self._base + 1
        self._retrain(features, adv, new_version)
        after = self._recall(self._booster(new_version), features, validation)

        verb = "recovered" if after > before else "did not generalize"
        summary = (
            f"Retrained fraud-v{new_version} with {len(adv)} adversarial samples; held-out "
            f"fraud recall {before:.3f} -> {after:.3f} ({verb})."
        )
        return PatchResult(
            patch_id=new_id("patch"), summary=summary,
            validated=bool(adv) and after >= before,
            holdout_detection_before=before, holdout_detection_after=after,
            audit=AuditTrace(Pillar.blue, summary, {
                "adversarial_samples": len(adv),
                "validation_attacks": len(validation),
                "validation_disjoint_from_training": True,
                "new_model_version": f"fraud-v{new_version}",
            }),
            new_model_version=f"fraud-v{new_version}",
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(status="green", detail={"blue": "fraud-retrain"})
