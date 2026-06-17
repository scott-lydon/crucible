"""Pluggable LLM client. The deterministic default keeps the whole tool runnable
offline with no API key; the Anthropic client is an optional, guarded enhancement.

Model IDs are configurable. Defaults reflect current Claude models
(claude-opus-4-8 / claude-sonnet-4-6); verify via the claude-api reference before
relying on pricing/limits.
"""

from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str, max_tokens: int = 512) -> str: ...

    @property
    def available(self) -> bool: ...


class NullLLM:
    """No LLM available. Deterministic engine paths do not call .complete()."""

    @property
    def available(self) -> bool:
        return False

    def complete(self, system: str, prompt: str, max_tokens: int = 512) -> str:
        raise RuntimeError("No LLM configured (running in deterministic mode).")


class AnthropicLLM:
    """Optional. Requires `pip install crucible-redteam[anthropic]` and ANTHROPIC_API_KEY."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.model = model
        self._client = None
        try:
            import anthropic  # noqa: PLC0415

            self._client = anthropic.Anthropic()
        except Exception:  # noqa: BLE001 — SDK missing or key absent: stay graceful
            self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def complete(self, system: str, prompt: str, max_tokens: int = 512) -> str:
        if self._client is None:
            raise RuntimeError("Anthropic client unavailable (install extra + set API key).")
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")


def make_llm(kind: str = "deterministic", model: str = "claude-sonnet-4-6") -> LLMClient:
    if kind == "anthropic":
        client = AnthropicLLM(model=model)
        if client.available:
            return client
    return NullLLM()
