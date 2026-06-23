"""Slice-14: the blue loop retrains the fraud classifier with the undetected-hack
samples and validates detection on a held-out attack set it never trained on. It
reports the TRUE before/after recall and never fakes a recovery — on the production
model the residual misses do not generalize (plan.md section 6), so ``validated`` is
honest. The mechanism (propose -> retrain -> held-out-validate -> new model version)
is what this slice proves."""

from __future__ import annotations

import asyncio

import lightgbm as lgb
import numpy as np

from modules.blue.agent import ARTIFACTS, FraudBlueAgent
from modules.targets.fraud.target import FraudTarget
from shared.datasets.fraud import load_splits
from shared.types.core import Attack
from shared.types.enums import Shape
from shared.types.ids import AttackId, RunId
from shared.types.sealed_spec import Obligation, SealedSpec

_SPEC = SealedSpec(
    spec_id="s", target_kind="fraud", shape=Shape.shape1_ml,
    obligations=(Obligation("c", "A fraudulent transaction must score high.", "label_match", {}),),
    invariants=(), holdout_generator_kind="data_partition",
)


def _missed_holdout_frauds() -> list[Attack]:
    splits = load_splits()
    features = splits.feature_names
    booster = lgb.Booster(model_file=str(ARTIFACTS / "fraud-v1.lgb"))
    missed: list[Attack] = []
    for idx in splits.y_holdout[splits.y_holdout == 1].index:
        row = {k: float(v) for k, v in splits.x_holdout.loc[idx].to_dict().items()}
        x = np.asarray([[row[f] for f in features]])
        if float(booster.predict(x)[0]) < 0.5:
            missed.append(Attack(AttackId("a"), RunId("r"), 0, "holdout-fraud", row, "",
                                 f"s{idx}", metadata={"true_label": 1}))
    return missed


def test_blue_retrains_validates_and_reports_honestly() -> None:
    missed = _missed_holdout_frauds()
    assert len(missed) >= 1, "expected the producer to miss some held-out frauds"

    blue = FraudBlueAgent(base_version=1)
    result = asyncio.run(blue.harden(_SPEC, RunId("r"), missed))

    # Mechanism: a new model version was produced and is loadable by the target adapter.
    assert result.new_model_version == "fraud-v2"
    assert (ARTIFACTS / "fraud-v2.lgb").exists()
    v2 = FraudTarget.load(2)
    assert v2.predict_sync(missed[0].payload)["label"] in (0, 1)

    # Honest measurement on a held-out attack set disjoint from training.
    assert 0.0 <= result.holdout_detection_before <= 1.0
    assert 0.0 <= result.holdout_detection_after <= 1.0
    assert result.audit.detail["validation_disjoint_from_training"] is True
    assert result.audit.detail["adversarial_samples"] == len(missed)
    assert "recall" in result.summary
    # validated reflects the true result (>= before with samples); never fabricated.
    assert result.validated == (result.holdout_detection_after >= result.holdout_detection_before)
