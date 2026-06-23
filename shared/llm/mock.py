"""Deterministic, offline LLM adapter for tests.

``MockProvider`` returns a fixed string with zero tokens and zero cost. No
network, no randomness — two calls with the same construction return identical
results.
"""

from collections.abc import Mapping

from shared.llm.base import LLMResponse


class MockProvider:
    """``LLMProvider`` that returns a fixed response. Deterministic; no network."""

    def __init__(self, text: str = '{"vote": "pass"}', model: str = "mock") -> None:
        self._text = text
        self._model = model

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        json_schema: Mapping[str, object] | None = None,
    ) -> LLMResponse:
        return LLMResponse(
            text=self._text,
            model="mock",
            input_tokens=0,
            output_tokens=0,
            dollars=0.0,
            raw={"mock": True},
        )
