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
from shared.types.agent import AgentConfig
from shared.types.core import Attack, AuditTrace
from shared.types.enums import Pillar
from shared.types.ids import RunId, new_id
from shared.types.results import HealthStatus, PatchResult
from shared.types.sealed_spec import SealedSpec

ARTIFACTS = Path(__file__).resolve().parents[2] / "artifacts"
THRESHOLD = 0.5
_UPWEIGHT = 50
# The fraud model has no prompt; its "config" carries the trained model VERSION so the
# co-evolution loop can version it like any agent (it hardens by RETRAINING, not rewriting).
_FRAUD_NOTE = "LightGBM fraud classifier; hardened by adversarial RETRAINING, not a prompt."


class FraudBlueAgent:
    """Co-evolution blue for the Shape-1 fraud model. Where the agent blue rewrites a system
    prompt, this HARDENS BY RETRAINING: each round it adds the frauds the model missed (the
    round's failures) to the training set, upweighted, retrains a new LightGBM version, and
    validates detection on a held-out fraud set fixed up front. A ConfigurableBlue whose config
    carries the model VERSION, so the co-evolution loop versions it like any agent."""

    def __init__(self, base_version: int = 1, *, tag: str = "", n_estimators: int = 200,
                 num_leaves: int = 31, train_frac: float = 1.0, upweight: int = _UPWEIGHT) -> None:
        self._base = base_version
        self._version = base_version
        self._tag = tag                          # "" production; "weak" the under-trained demo
        self._n_estimators = n_estimators
        self._num_leaves = num_leaves
        self._train_frac = train_frac
        # Upweight of the adversarial samples. A few samples at 50x OVERFIT and degrade held-out
        # recall; a gentler 5x (with accumulation across rounds) genuinely hardens (measured).
        self._upweight = upweight
        self._adv: list[dict[str, float]] = []   # adversarial frauds, accumulated across rounds

    @property
    def current_config(self) -> AgentConfig:
        name = "fraud-weak-model" if self._tag else "fraud-model"
        return AgentConfig(name=name, model="lightgbm-fraud",
                           system_prompt=_FRAUD_NOTE, description=_FRAUD_NOTE,
                           params={"tag": self._tag}, version=self._version)

    def reset(self) -> None:
        self._version = self._base
        self._adv = []

    def set_base(self, config: AgentConfig) -> None:
        self._base = config.version
        self._version = config.version
        self._adv = []

    def _stem(self, version: int) -> str:
        return f"fraud-{self._tag}-v{version}" if self._tag else f"fraud-v{version}"

    def _booster(self, version: int) -> lgb.Booster:
        return lgb.Booster(model_file=str(ARTIFACTS / f"{self._stem(version)}.lgb"))

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
        if self._train_frac < 1.0:   # keep the weak model weak: retrain on the same subsample
            rng = np.random.default_rng(42)
            idx = rng.choice(len(x_train), int(len(x_train) * self._train_frac), replace=False)
            x_train, y_train = x_train[idx], y_train[idx]
        if adv:
            x_adv = np.asarray([[float(r.get(f, 0.0)) for f in features] for r in adv])
            x_train = np.vstack([x_train, np.repeat(x_adv, self._upweight, axis=0)])
            y_train = np.concatenate([y_train, np.ones(x_adv.shape[0] * self._upweight, dtype=int)])
        spw = float((y_train == 0).sum()) / max(int((y_train == 1).sum()), 1)
        clf = lgb.LGBMClassifier(n_estimators=self._n_estimators, learning_rate=0.05,
                                 num_leaves=self._num_leaves, scale_pos_weight=spw,
                                 random_state=42, n_jobs=2, verbose=-1)
        clf.fit(x_train, y_train)
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        clf.booster_.save_model(str(ARTIFACTS / f"{self._stem(version)}.lgb"))
        meta = {"version": version, "tag": self._tag, "feature_names": features,
                "threshold": THRESHOLD, "trained_at": dt.datetime.now(dt.UTC).isoformat(),
                "blue_retrain": True, "adversarial_samples": len(adv)}
        (ARTIFACTS / f"{self._stem(version)}.meta.json").write_text(json.dumps(meta, indent=2))

    async def harden(
        self, spec: SealedSpec, run_id: RunId, catalog_slice: Sequence[Attack]
    ) -> PatchResult:
        splits = load_splits()
        features = list(splits.feature_names)
        # Held-out validation attacks: eval-split frauds, fixed up front, disjoint from the
        # adversarial samples (which come from the holdout split).
        validation = [
            {k: float(v) for k, v in splits.x_eval.loc[i].to_dict().items()}
            for i in splits.y_eval[splits.y_eval == 1].index
        ]
        current = self._recall(self._booster(self._version), features, validation)
        if not catalog_slice:
            summary = (f"No frauds slipped this round; fraud model left at v{self._version} "
                       f"(held-out recall {current:.3f}, no retraining).")
            return PatchResult(
                patch_id=new_id("patch"), summary=summary, validated=False,
                holdout_detection_before=current, holdout_detection_after=current,
                audit=AuditTrace(Pillar.blue, summary, {
                    "adversarial_samples": 0, "adopted": False,
                    "new_model_version": self._stem(self._version)}),
                new_model_version=self._stem(self._version))

        # Accumulate the round's missed frauds and retrain a fresh version from the base split
        # plus EVERY adversarial sample seen so far (cumulative hardening across rounds).
        self._adv.extend({k: float(v) for k, v in a.payload.items()} for a in catalog_slice)
        new_version = self._version + 1
        self._retrain(features, self._adv, new_version)
        after = self._recall(self._booster(new_version), features, validation)

        adopted = after >= current      # adopt unless the retrain regressed on held-out
        if adopted:
            self._version = new_version
        verb = ("recovered" if after > current
                else "held" if after == current else "did not generalize")
        summary = (
            f"Retrained {self._stem(new_version)} on {len(self._adv)} adversarial fraud(s); "
            f"held-out fraud recall {current:.3f} -> {after:.3f} ({verb})."
        )
        return PatchResult(
            patch_id=new_id("patch"), summary=summary,
            validated=after > current,
            holdout_detection_before=current, holdout_detection_after=after,
            audit=AuditTrace(Pillar.blue, summary, {
                "adversarial_samples": len(self._adv),
                "validation_attacks": len(validation),
                "validation_disjoint_from_training": True,
                "adopted": adopted,
                "new_model_version": self._stem(self._version),
            }),
            new_model_version=self._stem(self._version),
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(status="green", detail={"blue": "fraud-retrain"})
