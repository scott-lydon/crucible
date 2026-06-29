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

    # Mechanism: the retrain TRAINED a new model-version artifact (loadable), whether or not
    # the blue adopts it.
    assert (ARTIFACTS / "fraud-v2.lgb").exists()
    v2 = FraudTarget.load(2)
    assert v2.predict_sync(missed[0].payload)["label"] in (0, 1)

    # Honest measurement on a held-out attack set disjoint from training.
    assert 0.0 <= result.holdout_detection_before <= 1.0
    assert 0.0 <= result.holdout_detection_after <= 1.0
    assert result.audit.detail["validation_disjoint_from_training"] is True
    assert result.audit.detail["adversarial_samples"] == len(missed)
    assert "recall" in result.summary
    # validated == STRICT improvement, never fabricated. The blue ADOPTS the retrain (advances
    # the version) only when it did not regress on held-out; on the production model the residual
    # misses are idiosyncratic, so a regression keeps the agent at the prior version (honest).
    improved = result.holdout_detection_after >= result.holdout_detection_before
    assert result.validated == (result.holdout_detection_after > result.holdout_detection_before)
    assert result.new_model_version == ("fraud-v2" if improved else "fraud-v1")
    assert result.audit.detail["adopted"] is improved


def test_weak_fraud_blue_genuinely_hardens_and_adopts() -> None:
    """The deliberately UNDER-TRAINED co-evolution model has SYSTEMATIC gaps, so adversarial
    retraining genuinely lifts held-out recall and the blue ADOPTS the new version — the
    real-hardening counterpart to the production model's idiosyncratic, non-generalizing
    residual. This is what makes fraud_weak an honest co-evolution improvement demo."""
    from modules.targets.fraud.train import WEAK_PARAMS, WEAK_TAG, ensure_weak_model

    ensure_weak_model(1)
    splits = load_splits()
    feats = splits.feature_names
    booster = lgb.Booster(model_file=str(ARTIFACTS / "fraud-weak-v1.lgb"))
    missed: list[Attack] = []
    for idx in splits.y_holdout[splits.y_holdout == 1].index:
        row = {k: float(v) for k, v in splits.x_holdout.loc[idx].to_dict().items()}
        if float(booster.predict(np.asarray([[row[f] for f in feats]]))[0]) < 0.5:
            missed.append(Attack(AttackId("a"), RunId("r"), 0, "holdout-fraud", row, "",
                                 f"s{idx}", metadata={"true_label": 1}))
    assert len(missed) >= 8, "the weak model should miss many holdout frauds"

    blue = FraudBlueAgent(base_version=1, tag=WEAK_TAG, upweight=5, **WEAK_PARAMS)
    result = asyncio.run(blue.harden(_SPEC, RunId("r"), missed[:8]))

    # Genuine hardening: held-out recall climbs, the result validates, and the blue adopts v2.
    assert result.holdout_detection_after > result.holdout_detection_before
    assert result.validated is True
    assert result.new_model_version == "fraud-weak-v2"
    assert blue.current_config.version == 2
    assert blue.current_config.params["tag"] == WEAK_TAG
