"""Per-run LLM-call recording (cr-b4). Every Anthropic call should land in the
``llm_calls`` table so the dashboard's Inspect button can show its full trace
(prompt/response/tokens/cost) — but the modules that make the calls (red, judge,
target) hold no database session by design (constitution.md section 2). The bridge:

* ``RecordingLLM`` wraps any LLMClient and, on each call, appends a record to the
  *current run's* sink — a ``contextvars.ContextVar`` list. Because each run loop runs
  in its own asyncio task, the ContextVar is naturally task-local, so concurrent runs
  never cross-attribute calls even though they share the same wrapped clients.
* The loop opens a sink at run start (``record_into``) and drains it each round
  (``drain_records``), persisting the rows with the run + attack ids it owns."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from shared.llm.client import LLMClient, LLMResult

_SINK: ContextVar[list[LLMCallRecord] | None] = ContextVar("llm_call_sink", default=None)


@dataclass(frozen=True, slots=True)
class LLMCallRecord:
    pillar: str
    system: str
    prompt: str
    result: LLMResult


class RecordingLLM:
    """Decorator over an LLMClient that records every call into the active run sink.
    Transparent when no sink is set (e.g. spec compilation before a run starts)."""

    def __init__(self, inner: LLMClient, pillar: str) -> None:
        self._inner = inner
        self.pillar = pillar
        self.model = inner.model

    @property
    def available(self) -> bool:
        return self._inner.available

    async def complete(self, system: str, prompt: str, *, max_tokens: int = 512) -> LLMResult:
        result = await self._inner.complete(system, prompt, max_tokens=max_tokens)
        sink = _SINK.get()
        if sink is not None:
            sink.append(LLMCallRecord(self.pillar, system, prompt, result))
        return result


@contextmanager
def record_into(sink: list[LLMCallRecord]) -> Iterator[None]:
    """Bind ``sink`` as the active run's recorder for the duration of the block."""
    token = _SINK.set(sink)
    try:
        yield
    finally:
        _SINK.reset(token)


def drain_records() -> list[LLMCallRecord]:
    """Return the active sink's buffered records and clear it (call once per round).
    Empty when no sink is bound."""
    sink = _SINK.get()
    if sink is None:
        return []
    drained = list(sink)
    sink.clear()
    return drained
