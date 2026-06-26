"""Slice-9: the LLM judge votes pass/fail from the model's response, carries half a
vote, parses non-JSON robustly, and — being half a vote — can never decide a verdict
alone (spec US-4)."""

from __future__ import annotations

import asyncio

from modules.oracles.aggregator import aggregate
from modules.oracles.llm_judge.oracle import LLMJudgeOracle
from shared.llm.client import ScriptedLLM
from shared.types.core import Attack
from shared.types.enums import OracleKind, Shape
from shared.types.ids import AttackId, RunId
from shared.types.sealed_spec import Obligation, SealedSpec

_SPEC = SealedSpec(
    spec_id="s", target_kind="fraud", shape=Shape.shape1_ml,
    obligations=(Obligation("c", "A fraudulent transaction must score high.", "label_match", {}),),
    invariants=(), holdout_generator_kind="data_partition",
)
_ATTACK = Attack(AttackId("a"), RunId("r"), 0, "t", {"Amount": 1.0}, "", "seed")


def _judge(response: str) -> LLMJudgeOracle:
    return LLMJudgeOracle(ScriptedLLM(lambda _s, _p: response, model="scripted-judge"))


def test_judge_votes_violation() -> None:
    vote = asyncio.run(_judge('{"verdict": "violation", "reason": "missed a clear fraud"}')
                       .vote(_SPEC, _ATTACK, {"label": 0}))
    assert vote.fired is True
    assert vote.weight == 0.5
    assert vote.oracle is OracleKind.llm_judge
    assert "missed a clear fraud" in vote.reason


def test_judge_votes_ok() -> None:
    vote = asyncio.run(_judge('{"verdict": "ok", "reason": "consistent with spec"}')
                       .vote(_SPEC, _ATTACK, {"label": 1}))
    assert vote.fired is False


def test_judge_parses_non_json() -> None:
    vote = asyncio.run(_judge("This is clearly a VIOLATION of the stated obligation.")
                       .vote(_SPEC, _ATTACK, {"label": 0}))
    assert vote.fired is True


def test_judge_half_vote_cannot_decide_alone() -> None:
    fired = asyncio.run(_judge('{"verdict": "violation", "reason": "x"}')
                        .vote(_SPEC, _ATTACK, {"label": 0}))
    verdict = aggregate(RunId("r"), _ATTACK, {"label": 0}, [fired])
    assert fired.fired is True
    assert verdict.caught is False   # 0.5 < 2.0
