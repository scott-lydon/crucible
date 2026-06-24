"""Blue-loop unit tests: proposer, contamination guard, code-config, versioning.

No network and no database: the proposer runs on a scripted LLM, the held-out
contamination guard and detection rate are pure, and the retrainer's versioning
and code-config application touch only a temp directory. The real fraud retrain
and detection recovery are the opt-in test_blue_fraud_recovery.py (real data).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from modules.blue import (
    BlueProposer,
    HoldoutContamination,
    HoldoutValidator,
    Retrainer,
)
from shared.llm import LlmModel, ScriptedLlmClient
from shared.types import (
    Attack,
    AttackId,
    AuditTrace,
    BluePatch,
    Money,
    PatchId,
    RunId,
    TargetType,
)


def _attack(tactic: str = "t", payload: dict[str, Any] | None = None) -> Attack:
    return Attack(
        attack_id=AttackId.new(),
        run_id=RunId.new(),
        tactic=tactic,
        payload=payload if payload is not None else {"Amount": 100.0},
        succeeded=True,
        white_box=False,
        hybrid=False,
        dollars_spent=Money.zero(),
        audit=AuditTrace(summary="x", steps=()),
    )


def _scripted(text: str) -> ScriptedLlmClient:
    return ScriptedLlmClient(responses={LlmModel.SONNET: text})


async def test_fraud_proposal_carries_samples_provenance_and_train_config() -> None:
    attacks = [_attack(payload={"Amount": 1.0}), _attack(payload={"Amount": 2.0})]
    proposer = BlueProposer(
        llm=_scripted(
            '{"scale_pos_weight": 8, "n_estimators": 500, '
            '"learning_rate": 0.03, "reasoning": "upweight the missed pattern"}'
        )
    )
    patch = await proposer.propose_patch(TargetType.FRAUD, attacks)

    assert patch.kind == "retrain"
    assert patch.detail["adversarial_samples"] == [{"Amount": 1.0}, {"Amount": 2.0}]
    assert patch.detail["train_config"]["scale_pos_weight"] == 8.0
    assert patch.detail["train_config"]["n_estimators"] == 500
    assert patch.detail["provenance"] == [a.attack_id.value for a in attacks]


async def test_code_proposal_writes_a_reviewable_prompt_config_diff() -> None:
    attacks = [_attack(tactic="hardcode-test-outputs")]
    proposer = BlueProposer(
        llm=_scripted(
            '{"system_prompt_additions": "Never special-case the graded inputs.", '
            '"config": {"temperature": 0.0}, "reasoning": "block input-sniffing"}'
        )
    )
    patch = await proposer.propose_patch(TargetType.CODE_AGENT, attacks)

    assert patch.kind == "prompt_config"
    assert "Never special-case" in patch.detail["system_prompt_additions"]
    assert patch.detail["config"] == {"temperature": 0.0}
    assert patch.detail["provenance"] == [attacks[0].attack_id.value]


async def test_holdout_contamination_is_refused() -> None:
    shared = _attack()
    validator = HoldoutValidator()
    # The held-out set shares an attack with the training set: leakage, refused.
    with pytest.raises(HoldoutContamination):
        validator.assert_disjoint({shared.attack_id.value}, [shared, _attack()])
    # A disjoint set passes.
    validator.assert_disjoint({_attack().attack_id.value}, [_attack(), _attack()])


async def test_detection_rate_counts_attacks_at_or_above_threshold() -> None:
    validator = HoldoutValidator(threshold=0.5)
    attacks = [
        _attack(payload={"s": 0.9}),
        _attack(payload={"s": 0.1}),
        _attack(payload={"s": 0.6}),
        _attack(payload={"s": 0.2}),
    ]

    async def score(payload: dict[str, Any]) -> float:
        return float(payload["s"])

    rate = await validator.detection_rate(score, attacks)
    assert rate == 0.5  # two of four at or above 0.5


def test_next_fraud_version_is_one_past_the_highest(tmp_path: Path) -> None:
    (tmp_path / "fraud-v1.lgb").write_text("x")
    (tmp_path / "fraud-v3.lgb").write_text("x")
    assert Retrainer(artifacts_dir=tmp_path).next_fraud_version() == 4
    # Empty directory starts at version 1.
    assert Retrainer(artifacts_dir=tmp_path / "empty").next_fraud_version() == 1


def test_apply_code_config_assembles_the_new_agent_version() -> None:
    patch = BluePatch(
        patch_id=PatchId.new(),
        target_type=TargetType.CODE_AGENT,
        kind="prompt_config",
        detail={"system_prompt_additions": "Be strict.", "config": {"temperature": 0.0}},
        audit=AuditTrace(summary="x", steps=()),
    )
    applied = Retrainer().apply_code_config(patch, version=2)
    assert applied.version == 2
    assert applied.system_prompt == "Be strict."
    assert applied.config == {"temperature": 0.0}


def _tiny_fraud_csv(path: Path) -> None:
    """Write a tiny but valid two-class fraud dataset for a fast retrain.

    Just enough rows for a stratified 80/20 split with both classes present in
    each side; the model quality is irrelevant here, only the artifact the
    retrainer writes. Deterministic via a fixed seed.
    """
    rng = np.random.default_rng(0)
    legit = pd.DataFrame(
        {"V1": rng.normal(0.0, 1.0, 40), "V2": rng.normal(0.0, 1.0, 40), "Class": 0}
    )
    fraud = pd.DataFrame(
        {"V1": rng.normal(4.0, 1.0, 20), "V2": rng.normal(4.0, 1.0, 20), "Class": 1}
    )
    pd.concat([legit, fraud], ignore_index=True).to_csv(path, index=False)


def test_retrainer_bumps_version(tmp_path: Path) -> None:
    """A retrain with fraud-v1.lgb already present writes fraud-v2.lgb, not v1.

    Regression guard for the versioning bug (A4): the retrainer must emit the
    next integer past the highest artifact on disk and never overwrite the
    existing version. Uses a tiny synthetic dataset so the LightGBM pass is fast
    and self-contained (no network, no real Kaggle data).
    """
    sentinel = "the original v1 artifact bytes"
    (tmp_path / "fraud-v1.lgb").write_text(sentinel)
    csv_path = tmp_path / "creditcard.csv"
    _tiny_fraud_csv(csv_path)

    patch = BluePatch(
        patch_id=PatchId.new(),
        target_type=TargetType.FRAUD,
        kind="retrain",
        detail={"adversarial_samples": [], "train_config": {}, "provenance": []},
        audit=AuditTrace(summary="x", steps=()),
    )
    result = Retrainer(artifacts_dir=tmp_path, csv_path=csv_path).retrain_fraud(patch)

    assert result.version == 2
    assert (tmp_path / "fraud-v2.lgb").exists()
    # The pre-existing v1 artifact is left untouched, not overwritten.
    assert (tmp_path / "fraud-v1.lgb").read_text() == sentinel
