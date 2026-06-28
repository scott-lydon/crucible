"""PR #3 -> main port, Phase C (blue restructuring).

C1 FraudBlueAgent is split into BlueProposer + Retrainer + HoldoutValidator and its patch
   audit carries three labelled, time-ordered sections (Proposal, Retrain, Holdout
   validation).
C2 HoldoutValidator.assert_disjoint refuses a contaminated held-out set with a typed
   HoldoutContamination.
"""

from __future__ import annotations

import asyncio

import lightgbm as lgb
import numpy as np
import pytest
from fastapi.testclient import TestClient

from modules.blue.agent import ARTIFACTS, FraudBlueAgent
from modules.blue.errors import HoldoutContamination
from modules.blue.holdout_validator import HoldoutValidator
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


def _one_missed_holdout_fraud() -> Attack:
    splits = load_splits()
    features = splits.feature_names
    booster = lgb.Booster(model_file=str(ARTIFACTS / "fraud-v1.lgb"))
    for idx in splits.y_holdout[splits.y_holdout == 1].index:
        row = {k: float(v) for k, v in splits.x_holdout.loc[idx].to_dict().items()}
        x = np.asarray([[row[f] for f in features]])
        if float(booster.predict(x)[0]) < 0.5:
            return Attack(AttackId("atk-1"), RunId("r"), 0, "holdout-fraud", row, "",
                          f"s{idx}", metadata={"true_label": 1})
    raise AssertionError("expected at least one missed held-out fraud")


def test_c1_harden_emits_three_ordered_sections() -> None:
    blue = FraudBlueAgent(base_version=1)
    result = asyncio.run(blue.harden(_SPEC, RunId("r"), [_one_missed_holdout_fraud()]))
    sections = result.audit.detail["sections"]
    assert [s["label"] for s in sections] == ["Proposal", "Retrain", "Holdout validation"]
    # Timestamps are chronological: proposal before retrain before validation.
    times = [s["at"] for s in sections]
    assert times == sorted(times)
    # The holdout-validation section carries the before/after detection it measured.
    holdout = sections[2]["detail"]
    assert "holdout_detection_before" in holdout
    assert "holdout_detection_after" in holdout


def test_c2_holdout_validator_rejects_contamination() -> None:
    validator = HoldoutValidator()
    with pytest.raises(HoldoutContamination) as exc:
        validator.assert_disjoint({"atk-1", "atk-2"}, {"atk-2", "atk-9"})
    assert "overlap training" in str(exc.value)
    # A disjoint set is accepted silently.
    validator.assert_disjoint({"atk-1"}, {"holdout-eval-1"})


def test_c2_contamination_demo_route_seeds_a_refused_patch(client: TestClient) -> None:
    seeded = client.post("/admin/inject-contamination-demo").json()
    patch = client.get(f"/blue/{seeded['patch_id']}").json()
    assert "overlap training" in patch["contamination"]
    # No false recovery: the after-recall number is withheld for a contaminated patch.
    assert patch["safe_after"] is None
    assert patch["validated"] is False
