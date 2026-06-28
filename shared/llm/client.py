"""Pluggable LLM client. Three implementations behind one Protocol:

* ``ScriptedLLM`` — deterministic, free, no network. The default for unit tests and
  CI so the suite is fast and reproducible (spec US-15 mock-LLM mode).
* ``OpenRouterClient`` — routes the mandated Anthropic models (Sonnet 4.6 / Opus
  4.8) through OpenRouter, reading real per-call cost. Used for integration and the
  white-box pass.
* ``AnthropicClient`` — the direct Anthropic SDK, used if an ANTHROPIC_API_KEY is set.

Constitution section 1 mandates Anthropic models; OpenRouter is the transport, the
models are unchanged. ``record_llm_call`` persists every call to ``llm_calls`` so the
dashboard Inspect button has its row (constitution.md section 4)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar, Protocol, runtime_checkable

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from shared.persistence.models import LLMCallRow
from shared.types.ids import new_id

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass(frozen=True, slots=True)
class LLMResult:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    dollars: float


@runtime_checkable
class LLMClient(Protocol):
    model: str

    @property
    def available(self) -> bool: ...

    async def complete(self, system: str, prompt: str, *, max_tokens: int = 512) -> LLMResult: ...


class ScriptedLLM:
    """Deterministic stand-in. ``responder(system, prompt) -> str``. Records calls so
    tests can assert the LLM path fired without a key, and costs nothing."""

    def __init__(self, responder: Callable[[str, str], str], model: str = "scripted") -> None:
        self._responder = responder
        self.model = model
        self.calls: list[tuple[str, str]] = []

    @property
    def available(self) -> bool:
        return True

    async def complete(self, system: str, prompt: str, *, max_tokens: int = 512) -> LLMResult:
        self.calls.append((system, prompt))
        text = self._responder(system, prompt)
        return LLMResult(text=text, model=self.model, prompt_tokens=0, completion_tokens=0,
                         dollars=0.0)


class OpenRouterClient:
    """Async OpenRouter client, cost-metered and call-capped as a budget guard."""

    def __init__(self, model: str, api_key: str, *, max_calls: int = 2000,
                 timeout: float = 120.0) -> None:
        self.model = model
        self._api_key = api_key
        self._max_calls = max_calls
        self._timeout = timeout
        self.n_calls = 0
        self.cost = 0.0

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    async def complete(self, system: str, prompt: str, *, max_tokens: int = 512) -> LLMResult:
        if self.n_calls >= self._max_calls:
            raise RuntimeError(f"OpenRouter call cap reached ({self._max_calls}) — budget guard")
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "usage": {"include": True},
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                _OPENROUTER_URL,
                headers={"Authorization": f"Bearer {self._api_key}", "X-Title": "crucible"},
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
        if "error" in data:
            raise RuntimeError(f"OpenRouter error: {data['error']}")
        self.n_calls += 1
        usage = data.get("usage") or {}
        dollars = float(usage.get("cost", 0.0) or 0.0)
        self.cost += dollars
        return LLMResult(
            text=data["choices"][0]["message"]["content"] or "",
            model=self.model,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            dollars=dollars,
        )


class AnthropicClient:
    """Direct Anthropic SDK client. Used when ANTHROPIC_API_KEY is set, bypassing
    OpenRouter. Model names must NOT include the ``anthropic/`` prefix (e.g. pass
    ``claude-sonnet-4-6`` not ``anthropic/claude-sonnet-4.6``)."""

    # Anthropic pricing per 1M tokens (June 2026). Used for cost tracking only.
    _PRICING: ClassVar[dict[str, tuple[float, float]]] = {
        "claude-sonnet-4-6": (3.0, 15.0),
        "claude-opus-4-8": (15.0, 75.0),
        "claude-haiku-4-5-20251001": (0.80, 4.0),
    }

    def __init__(self, model: str, api_key: str, *, max_calls: int = 2000,
                 timeout: float = 120.0) -> None:
        # Strip the ``anthropic/`` prefix that OpenRouter models use, and normalise
        # the dotted form (``claude-sonnet-4.6``) to the dashed form the SDK expects.
        bare = model.removeprefix("anthropic/").replace(".", "-")
        self.model = bare
        self._api_key = api_key
        self._max_calls = max_calls
        self._timeout = timeout
        self.n_calls = 0
        self.cost = 0.0

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    async def complete(self, system: str, prompt: str, *, max_tokens: int = 512) -> LLMResult:
        if self.n_calls >= self._max_calls:
            raise RuntimeError(f"Anthropic call cap reached ({self._max_calls})")
        import anthropic
        client = anthropic.AsyncAnthropic(
            api_key=self._api_key,
            timeout=self._timeout,
        )
        msg = await client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        self.n_calls += 1
        text = msg.content[0].text if msg.content else ""
        p_tok = msg.usage.input_tokens
        c_tok = msg.usage.output_tokens
        in_price, out_price = self._PRICING.get(self.model, (3.0, 15.0))
        dollars = (p_tok * in_price + c_tok * out_price) / 1_000_000
        self.cost += dollars
        return LLMResult(
            text=text, model=self.model,
            prompt_tokens=p_tok, completion_tokens=c_tok, dollars=dollars,
        )


async def record_llm_call(
    session: AsyncSession,
    result: LLMResult,
    *,
    system: str,
    prompt: str,
    pillar: str,
    run_id: str | None = None,
    parent_action_id: str | None = None,
    seed: str = "",
    parsed_output: str = "",
) -> str:
    """Persist one LLM call's full trace surface. Returns the row id."""
    call_id = new_id("llm")
    session.add(
        LLMCallRow(
            id=call_id,
            run_id=run_id,
            pillar=pillar,
            model=result.model,
            prompt=f"SYSTEM:\n{system}\n\nUSER:\n{prompt}",
            raw_response=result.text,
            parsed_output=parsed_output,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            dollars=result.dollars,
            seed=seed,
            parent_action_id=parent_action_id,
        )
    )
    return call_id
