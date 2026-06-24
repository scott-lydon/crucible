"""Property-fuzz oracle tests: a scripted fuzz() plus the real sandbox."""

from __future__ import annotations

import shutil

import pytest

from modules.oracles.property_fuzz import PropertyFuzzOracle
from shared.llm import LlmModel, ScriptedLlmClient
from shared.sandbox import DockerSandbox
from shared.types import AuditTrace, SealedSpec, TargetOutput, VerdictDecision

pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker required for the sealed sandbox"
)

_FUZZ = (
    "def fuzz():\n"
    "    for _ in range(200):\n"
    "        a = random.randint(-100, 100)\n"
    "        b = random.randint(-100, 100)\n"
    "        assert add(a, b) == add(b, a), f'commutativity {a},{b}'\n"
    "        assert add(a, 0) == a, f'identity {a}'\n"
)


def _spec() -> SealedSpec:
    return SealedSpec.from_payload(
        {"title": "add", "obligations": [{"id": "o1", "description": "add(a, b) returns a + b"}]}
    )


def _output(source: str) -> TargetOutput:
    return TargetOutput(output=source, score=1.0, audit=AuditTrace(summary="t", steps=()))


def _oracle(fuzz: str = _FUZZ) -> PropertyFuzzOracle:
    return PropertyFuzzOracle(
        llm=ScriptedLlmClient(responses={LlmModel.SONNET: fuzz}), sandbox=DockerSandbox()
    )


async def test_pass_when_no_violation_found() -> None:
    vote = await _oracle().verify(_spec(), {}, _output("def add(a, b):\n    return a + b\n"))
    assert vote.decision == VerdictDecision.PASS


async def test_fail_finds_violation_on_broken_producer() -> None:
    vote = await _oracle().verify(_spec(), {}, _output("def add(a, b):\n    return a - b\n"))
    assert vote.decision == VerdictDecision.FAIL
    assert "violating input" in vote.reason


async def test_unavailable_when_no_fuzz_function() -> None:
    vote = await _oracle("no function here").verify(
        _spec(), {}, _output("def add(a, b):\n    return a + b\n")
    )
    assert vote.decision == VerdictDecision.UNAVAILABLE
