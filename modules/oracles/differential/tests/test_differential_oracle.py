"""Differential oracle tests: pure harness logic plus the real sandbox."""

from __future__ import annotations

import shutil

import pytest

from modules.oracles.differential import DifferentialOracle, build_diff_harness, parse_diff
from shared.llm import LlmModel, ScriptedLlmClient
from shared.sandbox import DockerSandbox, SandboxResult
from shared.types import AuditTrace, SealedSpec, TargetOutput, VerdictDecision

_needs_docker = pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker required for the sealed sandbox"
)

# Haiku returns the second implementation; Sonnet returns the comparison inputs.
_RESPONSES = {
    LlmModel.HAIKU: "def add(a, b):\n    return a + b",
    LlmModel.SONNET: "add(2, 3)\nadd(0, 0)\nadd(-5, 5)",
}


def _spec() -> SealedSpec:
    return SealedSpec.from_payload(
        {"title": "add", "obligations": [{"id": "o1", "description": "add(a, b) returns a + b"}]}
    )


def _output(source: str) -> TargetOutput:
    return TargetOutput(output=source, score=1.0, audit=AuditTrace(summary="t", steps=()))


def _oracle() -> DifferentialOracle:
    return DifferentialOracle(
        llm=ScriptedLlmClient(responses=_RESPONSES), sandbox=DockerSandbox()
    )


def test_build_diff_harness_embeds_both_sources_and_marker() -> None:
    harness = build_diff_harness("def f():\n    return 1", "def f():\n    return 2", ["f()"])
    assert "return 1" in harness
    assert "return 2" in harness
    assert "__CRUCIBLE_DIFF__" in harness


def test_parse_diff_extracts_report() -> None:
    result = SandboxResult(
        stdout='noise\n__CRUCIBLE_DIFF__{"total": 2, "mismatches": []}\n',
        stderr="",
        exit_code=0,
        job_id="x",
    )
    assert parse_diff(result) == {"total": 2, "mismatches": []}


def test_parse_diff_returns_none_without_marker() -> None:
    result = SandboxResult(stdout="nothing here", stderr="boom", exit_code=1, job_id="x")
    assert parse_diff(result) is None


async def test_unavailable_for_non_source_output() -> None:
    bad = TargetOutput(output={"fraud_probability": 0.1}, score=0.1, audit=AuditTrace("t", ()))
    vote = await _oracle().verify(_spec(), {}, bad)
    assert vote.decision == VerdictDecision.UNAVAILABLE


@_needs_docker
async def test_pass_when_two_families_agree() -> None:
    vote = await _oracle().verify(_spec(), {}, _output("def add(a, b):\n    return a + b\n"))
    assert vote.decision == VerdictDecision.PASS


@_needs_docker
async def test_fail_when_two_families_disagree() -> None:
    vote = await _oracle().verify(_spec(), {}, _output("def add(a, b):\n    return a - b\n"))
    assert vote.decision == VerdictDecision.FAIL
    assert "disagree" in vote.reason
