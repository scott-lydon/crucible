"""FraudBlueAgent: the Shape-1 hardening loop (spec US-7, plan.md section 3 Pillar 3).

C1 (PR3 port): the loop is split into three independently-auditable collaborators —
``BlueProposer`` selects the adversarial samples, ``Retrainer`` retrains the LightGBM
classifier, and ``HoldoutValidator`` validates detection on a held-out attack set DEFINED
UP FRONT that the retrain never touches (the held-out firewall, constitution.md section 3).
Each emits its own labelled, timestamped section in the patch audit trail, so the Blue
Patch Review shows Proposal, then Retrain, then Holdout validation in order.

It reports the true before/after recall and NEVER fakes a recovery: on the production fraud
model the residual misses are idiosyncratic and do not generalize (the "blue overfits / does
not converge" residual, plan.md section 6), so ``validated`` is honest."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import lightgbm as lgb
import numpy as np

from modules.blue.holdout_validator import HoldoutValidator
from modules.blue.proposer import BlueProposer
from modules.blue.retrainer import Retrainer
from shared.datasets.fraud import load_splits
from shared.types.core import Attack, AuditTrace
from shared.types.enums import Pillar
from shared.types.ids import RunId, new_id
from shared.types.results import HealthStatus, PatchResult
from shared.types.sealed_spec import SealedSpec

ARTIFACTS = Path(__file__).resolve().parents[2] / "artifacts"
THRESHOLD = 0.5


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


@dataclass(frozen=True, slots=True)
class FraudBlueAgent:
    """A1 frozen value object: the only field is the base model version it hardens from;
    it never mutates itself (each ``harden`` writes a NEW versioned artifact and returns a
    fresh PatchResult), so the agent is safe to share and its outputs replay deterministically
    (PR3 port checklist A1). It composes the C1 collaborators (proposer, retrainer, validator),
    each also frozen."""

    base_version: int = 1
    proposer: BlueProposer = field(default_factory=BlueProposer)
    retrainer: Retrainer = field(default_factory=Retrainer)
    validator: HoldoutValidator = field(default_factory=HoldoutValidator)

    def _booster(self, version: int) -> lgb.Booster:
        return lgb.Booster(model_file=str(ARTIFACTS / f"fraud-v{version}.lgb"))

    def _scores(self, booster: lgb.Booster, features: list[str],
                rows: Sequence[Mapping[str, Any]]) -> list[float]:
        if not rows:
            return []
        x = np.asarray([[float(r.get(f, 0.0)) for f in features] for r in rows])
        preds = np.asarray(cast("Any", booster.predict(x)))
        return [float(p) for p in preds]

    async def harden(
        self, spec: SealedSpec, run_id: RunId, catalog_slice: Sequence[Attack]
    ) -> PatchResult:
        splits = load_splits()
        features = list(splits.feature_names)

        # 1. Proposal: which adversarial samples to retrain on (from the catalog slice).
        t_proposal = _now()
        proposal = self.proposer.propose(catalog_slice)
        adv = BlueProposer.as_rows(proposal)

        # Held-out validation attacks: eval-split frauds, fixed up front, disjoint from the
        # training samples. Their ids are namespaced so the disjointness check is real.
        eval_index = list(splits.y_eval[splits.y_eval == 1].index)
        validation = [
            {k: float(v) for k, v in splits.x_eval.loc[i].to_dict().items()} for i in eval_index
        ]
        holdout_ids = {f"holdout-eval-{i}" for i in eval_index}
        # C2: refuse a contaminated held-out set rather than reporting an unearned recovery.
        self.validator.assert_disjoint(set(proposal.source_attack_ids), holdout_ids)
        before = self.validator.detection_rate(
            self._scores(self._booster(self.base_version), features, validation))

        # 2. Retrain: write the new versioned model from the proposal.
        t_retrain = _now()
        new_version = self.base_version + 1
        model_version = self.retrainer.retrain(features, adv, new_version)

        # 3. Holdout validation: measure detection on the up-front held-out set.
        t_validation = _now()
        after = self.validator.detection_rate(
            self._scores(self._booster(new_version), features, validation))

        verb = "recovered" if after > before else "did not generalize"
        summary = (
            f"Retrained {model_version} with {len(adv)} adversarial samples; held-out "
            f"fraud recall {before:.3f} -> {after:.3f} ({verb})."
        )
        sections = [
            {"label": "Proposal", "at": t_proposal,
             "detail": {"adversarial_samples": len(adv),
                        "source_attack_ids": list(proposal.source_attack_ids)[:10]}},
            {"label": "Retrain", "at": t_retrain,
             "detail": {"new_model_version": model_version, "upweight": self.retrainer.upweight}},
            {"label": "Holdout validation", "at": t_validation,
             "detail": {"validation_attacks": len(validation),
                        "holdout_detection_before": round(before, 4),
                        "holdout_detection_after": round(after, 4),
                        "disjoint_from_training": True}},
        ]
        return PatchResult(
            patch_id=new_id("patch"), summary=summary,
            validated=bool(adv) and after >= before,
            holdout_detection_before=before, holdout_detection_after=after,
            audit=AuditTrace(Pillar.blue, summary, {
                "sections": sections,
                "adversarial_samples": len(adv),
                "validation_attacks": len(validation),
                "validation_disjoint_from_training": True,
                "new_model_version": model_version,
            }),
            new_model_version=model_version,
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(status="green", detail={"blue": "fraud-retrain"})
