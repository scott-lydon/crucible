"""Held-out oracle tests: scripted LLM (canned asserts) plus the real sandbox.

The generate-compose-run-vote path runs in CI with Docker but no LLM call, so
the vote logic is exercised against the real sealed sandbox. The live LLM path
is covered separately by the opt-in interview-style runs.
"""

from __future__ import annotations

import shutil

import pytest

from modules.oracles.held_out import HeldOutOracle
from shared.llm import LlmModel, ScriptedLlmClient
from shared.sandbox import DockerSandbox
from shared.types import AuditTrace, SealedSpec, TargetOutput, VerdictDecision

pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="docker required to run held-out tests in the sealed sandbox",
)


def _spec() -> SealedSpec:
    return SealedSpec.from_payload(
        {"title": "add", "obligations": [{"id": "o1", "description": "add(a, b) returns a + b"}]}
    )


def _output(source: str) -> TargetOutput:
    return TargetOutput(output=source, score=1.0, audit=AuditTrace(summary="t", steps=()))


async def test_passes_when_implementation_satisfies_generated_tests() -> None:
    asserts = "assert add(2, 3) == 5\nassert add(0, 0) == 0"
    oracle = HeldOutOracle(
        llm=ScriptedLlmClient(responses={LlmModel.OPUS: asserts}),
        sandbox=DockerSandbox(),
    )
    vote = await oracle.verify(_spec(), {}, _output("def add(a, b):\n    return a + b\n"))
    assert vote.decision == VerdictDecision.PASS
    assert vote.oracle_name == "held_out"
    assert vote.weight == 1.0


async def test_fails_when_implementation_violates_generated_tests() -> None:
    oracle = HeldOutOracle(
        llm=ScriptedLlmClient(responses={LlmModel.OPUS: "assert add(2, 3) == 5"}),
        sandbox=DockerSandbox(),
    )
    vote = await oracle.verify(_spec(), {}, _output("def add(a, b):\n    return a - b\n"))
    assert vote.decision == VerdictDecision.FAIL
    assert "failed" in vote.reason


async def test_unavailable_when_output_is_not_source() -> None:
    oracle = HeldOutOracle(llm=ScriptedLlmClient(), sandbox=DockerSandbox())
    bad = TargetOutput(
        output={"not": "source"}, score=None, audit=AuditTrace(summary="t", steps=())
    )
    vote = await oracle.verify(_spec(), {}, bad)
    assert vote.decision == VerdictDecision.UNAVAILABLE
