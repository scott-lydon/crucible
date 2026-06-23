"""Tests for the LLM provider port and its adapters.

Three groups:

* ``AnthropicApiProvider`` against a FAKE client — a unit test of the adapter's
  request construction and response parsing (no network).
* ``MockProvider`` — deterministic, offline.
* A gated live smoke test — skipped unless ``ANTHROPIC_API_KEY`` is set. This is
  the only test that costs money; it stays skipped in CI without a key.
"""

import os
from collections.abc import Mapping
from typing import Any

import pytest

from shared.llm import AnthropicApiProvider, LLMProvider, MockProvider
from shared.llm.anthropic_api import _price_for


# --- Fakes for the AnthropicApiProvider unit test ---------------------------


class _FakeBlock:
    def __init__(self, type_: str, text: str) -> None:
        self.type = type_
        self.text = text


class _FakeUsage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeResponse:
    def __init__(self) -> None:
        self.content = [_FakeBlock("text", "hello")]
        self.usage = _FakeUsage(input_tokens=1000, output_tokens=500)
        self.model = "claude-opus-4-8"

    def to_dict(self) -> dict[str, object]:
        return {}


class _FakeMessages:
    def __init__(self) -> None:
        self.recorded_kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.recorded_kwargs = kwargs
        return _FakeResponse()


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


# --- AnthropicApiProvider unit test -----------------------------------------


def test_anthropic_provider_with_fake_client() -> None:
    fake = _FakeClient()
    provider = AnthropicApiProvider(client=fake)

    resp = provider.complete("ping", system="be terse", max_tokens=256)

    kwargs = fake.messages.recorded_kwargs
    # (1) required fields present; rejected sampling params absent.
    assert kwargs["model"] == "claude-opus-4-8"
    assert kwargs["max_tokens"] == 256
    assert kwargs["messages"] == [{"role": "user", "content": "ping"}]
    for forbidden in ("temperature", "top_p", "top_k", "budget_tokens"):
        assert forbidden not in kwargs, f"{forbidden} must not be sent to Opus 4.8"

    # (2) text concatenation from text blocks.
    assert resp.text == "hello"
    assert resp.model == "claude-opus-4-8"
    assert resp.input_tokens == 1000
    assert resp.output_tokens == 500

    # (3) cost calc: 1000 input + 500 output at Opus 4.8 rates == 0.0175.
    assert resp.dollars == round(1000 * 5e-6 + 500 * 25e-6, 6)
    assert resp.dollars == 0.0175
    assert resp.raw == {}


def test_pricing_is_model_aware() -> None:
    # Per-token ($/token) pricing must reflect the actual model, not Opus for all.
    assert _price_for("claude-opus-4-8") == (5.0 / 1_000_000, 25.0 / 1_000_000)
    assert _price_for("claude-sonnet-4-6") == (3.0 / 1_000_000, 15.0 / 1_000_000)
    assert _price_for("claude-haiku-4-5") == (1.0 / 1_000_000, 5.0 / 1_000_000)
    # Unknown model falls back to Opus pricing (conservative — never under-reports).
    assert _price_for("mystery-model") == (5.0 / 1_000_000, 25.0 / 1_000_000)


def test_anthropic_provider_passes_json_schema_output_config() -> None:
    fake = _FakeClient()
    provider = AnthropicApiProvider(client=fake)

    schema: Mapping[str, object] = {
        "type": "object",
        "properties": {"vote": {"type": "string"}},
        "required": ["vote"],
        "additionalProperties": False,
    }
    provider.complete("decide", json_schema=schema)

    # (4) json_schema becomes output_config with a json_schema format.
    output_config = fake.messages.recorded_kwargs["output_config"]
    assert output_config["format"]["type"] == "json_schema"
    assert output_config["format"]["schema"] == dict(schema)


def test_anthropic_provider_omits_system_and_output_config_when_unset() -> None:
    fake = _FakeClient()
    provider = AnthropicApiProvider(client=fake)

    provider.complete("plain")

    kwargs = fake.messages.recorded_kwargs
    assert "system" not in kwargs
    assert "output_config" not in kwargs


# --- MockProvider test ------------------------------------------------------


def test_mock_provider_is_deterministic() -> None:
    provider: LLMProvider = MockProvider(text='{"vote": "fail"}')

    first = provider.complete("anything")
    second = provider.complete("something else", system="ignored", max_tokens=99)

    assert first.text == '{"vote": "fail"}'
    assert first.model == "mock"
    assert first.dollars == 0.0
    assert first.input_tokens == 0
    assert first.output_tokens == 0
    assert first.raw == {"mock": True}
    # Deterministic across two calls.
    assert first == second


def test_mock_provider_default_text() -> None:
    assert MockProvider().complete("x").text == '{"vote": "pass"}'


# --- Gated live smoke test (only test that costs money) ---------------------


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="no ANTHROPIC_API_KEY",
)
def test_live_smoke() -> None:
    provider = AnthropicApiProvider()
    resp = provider.complete("Reply with the single word: pong", max_tokens=16)
    assert resp.text != ""
    assert resp.input_tokens > 0
    assert resp.dollars > 0
