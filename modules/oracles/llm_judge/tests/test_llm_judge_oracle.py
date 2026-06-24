"""LLM judge oracle tests: scripted LLM, no sandbox.

The judge runs nothing in the sandbox, so these need no docker. A scripted
client returns canned judge responses and the vote logic is exercised against
them. The live LLM path is covered by the opt-in interview-style run in
tests/integration/test_llm_judge_oracle.py.
"""

from __future__ import annotations

import pytest

from modules.oracles.llm_judge import LlmJudgeOracle, parse_judge_response
from shared.llm import LlmModel, ScriptedLlmClient
from shared.types import AuditTrace, SealedSpec, TargetOutput, VerdictDecision


def _spec() -> SealedSpec:
    return SealedSpec.from_payload(
        {
            "title": "add",
            "obligations": [{"id": "o1", "description": "add(a, b) returns a + b"}],
        }
    )


def _output(artifact: object) -> TargetOutput:
    return TargetOutput(output=artifact, score=None, audit=AuditTrace(summary="t", steps=()))


def _judge(text: str) -> LlmJudgeOracle:
    return LlmJudgeOracle(llm=ScriptedLlmClient(responses={LlmModel.OPUS: text}))


async def test_votes_pass_when_judge_says_pass() -> None:
    judge = _judge('{"decision": "pass", "reason": "It returns the sum."}')
    vote = await judge.verify(_spec(), {}, _output("def add(a, b):\n    return a + b\n"))
    assert vote.decision == VerdictDecision.PASS
    assert vote.oracle_name == "llm_judge"
    assert vote.weight == 0.5
    assert vote.obligation_id == "o1"
    assert "sum" in vote.reason


async def test_votes_fail_when_judge_says_fail() -> None:
    judge = _judge('{"decision": "fail", "reason": "It subtracts instead of adding."}')
    vote = await judge.verify(_spec(), {}, _output("def add(a, b):\n    return a - b\n"))
    assert vote.decision == VerdictDecision.FAIL
    assert "subtracts" in vote.reason


async def test_unavailable_when_response_is_not_a_verdict() -> None:
    judge = _judge("I think it looks fine to me, no JSON here.")
    vote = await judge.verify(_spec(), {}, _output("def add(a, b):\n    return a + b\n"))
    assert vote.decision == VerdictDecision.UNAVAILABLE
    assert "not a parseable" in vote.reason


async def test_unavailable_when_artifact_is_empty() -> None:
    judge = _judge('{"decision": "pass", "reason": "unused"}')
    vote = await judge.verify(_spec(), {}, _output("   "))
    assert vote.decision == VerdictDecision.UNAVAILABLE
    assert "empty artifact" in vote.reason


async def test_renders_structured_output_so_the_judge_is_target_agnostic() -> None:
    # A fraud-style structured artifact, not source code: the judge must still
    # read it and vote, proving the oracle is not code-only.
    judge = _judge('{"decision": "fail", "reason": "Probability 0.02 misses a known fraud."}')
    vote = await judge.verify(_spec(), {}, _output({"fraud_probability": 0.02, "label": "legit"}))
    assert vote.decision == VerdictDecision.FAIL
    assert "Probability" in vote.reason


def test_parse_judge_response_unwraps_a_json_fence() -> None:
    fenced = '```json\n{"decision": "pass", "reason": "ok"}\n```'
    parsed = parse_judge_response(fenced)
    assert parsed == (VerdictDecision.PASS, "ok")


@pytest.mark.parametrize(
    "text",
    [
        '{"decision": "maybe", "reason": "hedging"}',  # decision not pass/fail
        '{"decision": "pass"}',  # no reason
        '{"decision": "pass", "reason": ""}',  # empty reason
        '{"reason": "missing decision"}',  # no decision
        "not json at all",  # no object
        '{"decision": 1, "reason": "wrong type"}',  # non-string decision
    ],
)
def test_parse_judge_response_returns_none_on_malformed(text: str) -> None:
    assert parse_judge_response(text) is None
