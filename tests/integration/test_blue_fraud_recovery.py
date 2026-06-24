"""Slice 14 done-criterion (fraud): one blue round recovers detection, real data.

Opt-in (CRUCIBLE_RUN_SLOW_TESTS=1 plus the real creditcard.csv present), since it
retrains LightGBM on the full Kaggle dataset. No synthetic data.

Method, honest: the held-out "attacks" are real frauds the committed v1 model
misses (false negatives at the 0.5 threshold, so v1's detection on them is 0 by
construction). The blue patch folds a DISJOINT set of missed frauds into training
(oversampled) and the proposer retrains v2. The held-out validator confirms the
held-out frauds never appear in the patch's training-attack provenance (the
contamination guard) and measures detection before (v1) and after (v2). The
blue-loop value proposition is exactly this: the model catches frauds it
previously missed after hardening on the missed pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from modules.blue import BlueProposer, Retrainer, fraud_scorer
from modules.blue.retrainer import DEFAULT_ARTIFACTS_DIR, DEFAULT_CSV_PATH
from shared.llm import LlmModel, ScriptedLlmClient
from shared.types import (
    Attack,
    AttackId,
    AuditTrace,
    Money,
    RunId,
    TargetType,
)

_V1 = DEFAULT_ARTIFACTS_DIR / "fraud-v1.lgb"
_should_run = (
    os.environ.get("CRUCIBLE_RUN_SLOW_TESTS") == "1"
    and DEFAULT_CSV_PATH.exists()
    and _V1.exists()
)

pytestmark = pytest.mark.skipif(
    not _should_run,
    reason="set CRUCIBLE_RUN_SLOW_TESTS=1 with the real creditcard.csv and fraud-v1.lgb",
)


def _attack(payload: dict[str, float]) -> Attack:
    return Attack(
        attack_id=AttackId.new(),
        run_id=RunId.new(),
        tactic="missed-fraud",
        payload=payload,
        succeeded=True,
        white_box=False,
        hybrid=False,
        dollars_spent=Money.zero(),
        audit=AuditTrace(summary="real missed fraud", steps=()),
    )


async def test_one_blue_round_recovers_detection_on_held_out_attacks(
    tmp_path: Path,
) -> None:
    frame = pd.read_csv(DEFAULT_CSV_PATH)
    features = [c for c in frame.columns if c != "Class"]
    frauds = frame[frame["Class"] == 1]

    score_v1 = fraud_scorer(_V1)
    missed: list[dict[str, float]] = []
    for _, row in frauds.iterrows():
        payload = {f: float(row[f]) for f in features}
        if await score_v1(payload) < 0.5:
            missed.append(payload)

    assert len(missed) >= 20, f"need missed frauds to harden against; got {len(missed)}"
    split = len(missed) * 7 // 10
    train_attacks = [_attack(p) for p in missed[:split]]
    holdout_attacks = [_attack(p) for p in missed[split:]]

    proposer = BlueProposer(
        llm=ScriptedLlmClient(
            responses={
                LlmModel.SONNET: '{"scale_pos_weight": 25, "n_estimators": 300, '
                '"learning_rate": 0.05, "reasoning": "upweight the missed pattern"}'
            }
        ),
        retrainer=Retrainer(artifacts_dir=tmp_path, csv_path=DEFAULT_CSV_PATH),
        base_fraud_artifact=_V1,
    )
    patch = await proposer.propose_patch(TargetType.FRAUD, train_attacks)
    result = await proposer.validate_on_holdout(patch, holdout_attacks)

    assert result["detection_before"] == 0.0  # held-out frauds are v1 false negatives
    assert result["detection_after"] > result["detection_before"], result
    assert result["recovered"] is True, result
    assert (tmp_path / f"fraud-v{result['version']}.lgb").exists()
