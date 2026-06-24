"""Unit tests for CodeAgentTarget. Uses the scripted LLM client, no real CLI."""

from __future__ import annotations

from modules.targets.code_agent import (
    CodeAgentTarget,
    extract_python_source,
    is_valid_python,
)
from shared.llm import LlmModel, ScriptedLlmClient
from shared.types import SealedSpec


def _spec() -> SealedSpec:
    return SealedSpec.from_payload(
        {
            "title": "add two integers",
            "obligations": [{"id": "o1", "description": "return the sum"}],
        }
    )


def test_extract_plain_source() -> None:
    assert extract_python_source("def f():\n    return 1") == "def f():\n    return 1"


def test_extract_fenced_python_block() -> None:
    fenced = "```python\ndef f():\n    return 1\n```"
    assert extract_python_source(fenced) == "def f():\n    return 1"


def test_extract_fenced_block_without_language() -> None:
    assert extract_python_source("```\nx = 1\n```") == "x = 1"


def test_is_valid_python_true_and_false() -> None:
    assert is_valid_python("def f():\n    return 1")
    assert not is_valid_python("def (:")


async def test_submit_returns_valid_source_and_score_one() -> None:
    code = "def add(a, b):\n    return a + b\n"
    target = CodeAgentTarget(llm=ScriptedLlmClient(responses={LlmModel.SONNET: code}))
    out = await target.submit(_spec(), {"a": 1, "b": 2})
    assert out.output == code.strip()
    assert out.score == 1.0
    assert is_valid_python(out.output)


async def test_submit_scores_zero_on_invalid_code() -> None:
    target = CodeAgentTarget(llm=ScriptedLlmClient(responses={LlmModel.SONNET: "def (:"}))
    out = await target.submit(_spec(), {})
    assert out.score == 0.0


async def test_query_target_returns_validity_signal() -> None:
    target = CodeAgentTarget(llm=ScriptedLlmClient(responses={LlmModel.SONNET: "x = 1\n"}))
    assert await target.query_target({"task": "set x to 1"}) == 1.0


async def test_self_test_mock_client_is_green() -> None:
    result = await CodeAgentTarget(llm=ScriptedLlmClient()).self_test()
    assert result.status.value == "green"
    assert result.detail["mode"] == "mock"
