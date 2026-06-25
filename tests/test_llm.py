"""Unit tests for the LLM layer. No CLI call, no network, no database.

The parser is tested against a fixture matching the real
`claude --output-format json` shape, so it verifies our parsing logic rather
than a mocked result. The live CLI path is covered by
tests/integration/test_llm_cli.py.
"""

from __future__ import annotations

import json

import pytest

from shared.config import Settings
from shared.llm import (
    ClaudeCliClient,
    LlmCallError,
    LlmModel,
    ScriptedLlmClient,
    get_llm_client,
    parse_cli_json,
)

# Subset of a real `claude -p --output-format json` payload.
_REAL_SHAPE = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "ok",
        "total_cost_usd": 0.0123,
        "usage": {"input_tokens": 3, "output_tokens": 4},
        "session_id": "abc123",
    }
).encode("utf-8")


def test_parse_cli_json_extracts_text_cost_and_usage() -> None:
    result = parse_cli_json(_REAL_SHAPE, LlmModel.SONNET)
    assert result.text == "ok"
    assert result.model is LlmModel.SONNET
    assert str(result.dollars) == "$0.0123"
    assert result.tokens_in == 3
    assert result.tokens_out == 4
    assert result.session_id == "abc123"


def test_parse_cli_json_raises_on_non_json() -> None:
    with pytest.raises(LlmCallError, match="not JSON"):
        parse_cli_json(b"not json at all", LlmModel.OPUS)


def test_parse_cli_json_raises_on_cli_error_flag() -> None:
    payload = json.dumps({"is_error": True, "result": "rate limited"}).encode("utf-8")
    with pytest.raises(LlmCallError, match="reported an error"):
        parse_cli_json(payload, LlmModel.SONNET)


def test_parse_cli_json_raises_when_result_missing() -> None:
    payload = json.dumps({"is_error": False, "usage": {}}).encode("utf-8")
    with pytest.raises(LlmCallError, match="no string 'result'"):
        parse_cli_json(payload, LlmModel.SONNET)


async def test_scripted_client_returns_canned_text_and_zero_cost() -> None:
    client = ScriptedLlmClient(responses={LlmModel.OPUS: "verdict: pass"})
    result = await client.call("anything", model=LlmModel.OPUS)
    assert result.text == "verdict: pass"
    assert result.dollars.dollars == 0
    assert result.raw["mock"] is True


def test_factory_returns_scripted_client_when_mock_enabled() -> None:
    client = get_llm_client(Settings(mock_llm=True))
    assert isinstance(client, ScriptedLlmClient)


def test_factory_returns_cli_client_when_mock_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Force the CLI-available branch so the test exercises the selection logic
    # deterministically instead of depending on whether the `claude` binary
    # happens to be installed on the runner (it is not, in CI).
    monkeypatch.setattr("shared.llm.client._cli_available", lambda: True)
    client = get_llm_client(Settings(mock_llm=False))
    assert isinstance(client, ClaudeCliClient)
