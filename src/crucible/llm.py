"""Pluggable LLM client. The deterministic default keeps the whole tool runnable
offline with no API key; the Anthropic client is an optional, guarded enhancement.

Model IDs are configurable. Defaults reflect current Claude models
(claude-opus-4-8 / claude-sonnet-4-6); verify via the claude-api reference before
relying on pricing/limits.
"""

from __future__ import annotations

import json
import os
import urllib.request
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


class ScriptedLLM:
    """Deterministic LLM stand-in for testing the LLM code paths offline.

    `responder(system, prompt) -> str`. Records calls so tests can assert the
    LLM paths actually fired without needing an API key.
    """

    def __init__(self, responder):
        self._responder = responder
        self.calls: list[tuple[str, str]] = []

    @property
    def available(self) -> bool:
        return True

    def complete(self, system: str, prompt: str, max_tokens: int = 512) -> str:
        self.calls.append((system, prompt))
        return self._responder(system, prompt)


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


class OpenRouterLLM:
    """OpenAI-compatible client for OpenRouter (https://openrouter.ai), stdlib-only.

    Tracks call count + cumulative cost (OpenRouter returns per-call cost) and
    hard-caps the number of calls as a budget guard. Reads OPENROUTER_API_KEY.
    """

    def __init__(self, model: str = "anthropic/claude-3.5-haiku", api_key: str | None = None,
                 base_url: str = "https://openrouter.ai/api/v1", max_calls: int = 300,
                 timeout: float = 60.0):
        self.model = model
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.max_calls = max_calls
        self.timeout = timeout
        self.n_calls = 0
        self.cost = 0.0

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: list[dict], max_tokens: int = 512) -> str:
        """Full multi-turn chat. `messages` = [{"role","content"}, ...]."""
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        if self.n_calls >= self.max_calls:
            raise RuntimeError(f"OpenRouter call cap reached ({self.max_calls}) — budget guard")
        body = json.dumps({"model": self.model, "max_tokens": max_tokens,
                           "messages": messages}).encode()
        req = urllib.request.Request(  # noqa: S310
            f"{self.base_url}/chat/completions", data=body,
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json", "X-Title": "crucible"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            d = json.loads(r.read().decode())
        self.n_calls += 1
        self.cost += float((d.get("usage") or {}).get("cost", 0.0) or 0.0)
        return d["choices"][0]["message"]["content"]

    def complete(self, system: str, prompt: str, max_tokens: int = 512) -> str:
        return self.chat([{"role": "system", "content": system},
                          {"role": "user", "content": prompt}], max_tokens=max_tokens)

    def chat_tools(self, messages: list[dict], tools: list[dict], max_tokens: int = 400) -> dict:
        """OpenAI-style function calling. Returns {'text', 'tool_calls':[{name,args}]}."""
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        if self.n_calls >= self.max_calls:
            raise RuntimeError(f"OpenRouter call cap reached ({self.max_calls}) — budget guard")
        body = json.dumps({"model": self.model, "max_tokens": max_tokens,
                           "messages": messages, "tools": tools}).encode()
        req = urllib.request.Request(  # noqa: S310
            f"{self.base_url}/chat/completions", data=body,
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json", "X-Title": "crucible"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            d = json.loads(r.read().decode())
        self.n_calls += 1
        self.cost += float((d.get("usage") or {}).get("cost", 0.0) or 0.0)
        msg = d["choices"][0]["message"]
        calls = []
        for tc in (msg.get("tool_calls") or []):
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:  # noqa: BLE001
                args = {}
            calls.append({"name": fn.get("name", ""), "args": args})
        return {"text": msg.get("content") or "", "tool_calls": calls}


def make_llm(kind: str = "deterministic", model: str = "claude-sonnet-4-6") -> LLMClient:
    if kind == "anthropic":
        client = AnthropicLLM(model=model)
        if client.available:
            return client
    if kind == "openrouter":
        if "/" not in model:
            model = "anthropic/claude-3.5-haiku"
        client = OpenRouterLLM(model=model)
        if client.available:
            return client
    return NullLLM()
