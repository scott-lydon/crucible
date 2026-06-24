"""Metamorphic oracle tests: scripted relations plus the real sandbox."""

from __future__ import annotations

import shutil

import pytest

from modules.oracles.metamorphic import MetamorphicOracle
from shared.llm import LlmModel, ScriptedLlmClient
from shared.sandbox import DockerSandbox
from shared.types import AuditTrace, SealedSpec, TargetOutput, VerdictDecision

pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="docker required to run metamorphic relations in the sealed sandbox",
)

_RULES = "assert add(2, 3) == add(3, 2)\nassert add(5, 0) == 5\nassert add(1, 1) == add(0, 2)"


def _spec() -> SealedSpec:
    return SealedSpec.from_payload(
        {
            "title": "add",
            "obligations": [{"id": "o1", "description": "add(a, b) returns a + b"}],
            "invariants": [{"id": "i1", "description": "add is commutative"}],
        }
    )


def _output(source: str) -> TargetOutput:
    return TargetOutput(output=source, score=1.0, audit=AuditTrace(summary="t", steps=()))


def _oracle(rules: str = _RULES) -> MetamorphicOracle:
    return MetamorphicOracle(
        llm=ScriptedLlmClient(responses={LlmModel.SONNET: rules}),
        sandbox=DockerSandbox(),
    )


async def test_generate_rules_parses_assert_lines() -> None:
    rules = await _oracle().generate_rules(_spec())
    assert len(rules) == 3


async def test_passes_when_all_relations_hold() -> None:
    vote = await _oracle().verify(_spec(), {}, _output("def add(a, b):\n    return a + b\n"))
    assert vote.decision == VerdictDecision.PASS


async def test_fails_when_a_relation_breaks() -> None:
    vote = await _oracle().verify(_spec(), {}, _output("def add(a, b):\n    return a - b\n"))
    assert vote.decision == VerdictDecision.FAIL


async def test_unavailable_when_too_few_relations() -> None:
    vote = await _oracle("assert add(2, 3) == add(3, 2)").verify(
        _spec(), {}, _output("def add(a, b):\n    return a + b\n")
    )
    assert vote.decision == VerdictDecision.UNAVAILABLE
