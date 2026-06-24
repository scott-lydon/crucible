"""Slice 9 live proof: real Opus judges a correct and a wrong implementation.

Opt-in (CRUCIBLE_RUN_LLM_TESTS=1 plus `claude` on PATH), since it calls the
real CLI. No mock: this is the real judge reading real code and voting. The
judge runs nothing in the sandbox, so no docker is required.
"""

from __future__ import annotations

import os
import shutil

import pytest

from modules.oracles.llm_judge import LlmJudgeOracle
from shared.llm import ClaudeCliClient
from shared.types import AuditTrace, SealedSpec, TargetOutput, VerdictDecision

_should_run = os.environ.get("CRUCIBLE_RUN_LLM_TESTS") == "1" and shutil.which("claude")

pytestmark = pytest.mark.skipif(
    not _should_run,
    reason="set CRUCIBLE_RUN_LLM_TESTS=1 and have the claude CLI on PATH to run",
)


def _spec() -> SealedSpec:
    return SealedSpec.from_payload(
        {
            "title": "add two integers",
            "obligations": [
                {"id": "o1", "description": "define add(a, b) that returns a + b"}
            ],
        }
    )


def _output(source: str) -> TargetOutput:
    return TargetOutput(
        output=source, score=None, audit=AuditTrace(summary="produced", steps=())
    )


async def test_judge_passes_correct_and_fails_wrong() -> None:
    judge = LlmJudgeOracle(llm=ClaudeCliClient())

    good = await judge.verify(_spec(), {}, _output("def add(a, b):\n    return a + b\n"))
    assert good.decision == VerdictDecision.PASS, good.reason
    assert good.weight == 0.5

    bad = await judge.verify(_spec(), {}, _output("def add(a, b):\n    return a - b\n"))
    assert bad.decision == VerdictDecision.FAIL, bad.reason
