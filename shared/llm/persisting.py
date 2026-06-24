"""A persisting decorator for ``LLMProvider``.

``PersistingLLMProvider`` wraps any ``LLMProvider`` and writes one ``llm_calls``
row AROUND each ``complete(...)`` — capturing the prompt, system, raw response,
token counts, and dollar cost so the dashboard's Inspect button (US-2/US-3) has
real data and the dollars-per-caught-hack tile (US-10) can be computed. It is a
pure decorator: it makes NO extra model call, and returns the inner response
unchanged.

The seam is awkward: ``LLMProvider.complete`` is synchronous and is called from
inside the orchestrator's *running* async event loop (the oracle/adversary
``vote``/``mutate`` methods are invoked synchronously inside ``run_loop``). We
cannot ``await`` the async session there, and ``asyncio.run`` would fail
("cannot be called from a running event loop"). So the persistence write is
driven on a DEDICATED background event loop running in its own thread; the
sync ``complete`` blocks on the result. This keeps the write on the same async
SQLAlchemy machinery the rest of the app uses (no second sync DB driver).

Fail-loud-but-don't-crash: a persistence error is logged and swallowed so a
recording failure never aborts a run — but the call IS recorded on the happy
path (we never silently drop records on a healthy DB).
"""

import asyncio
import json
import threading
from collections.abc import Coroutine, Mapping
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.llm.base import LLMProvider, LLMResponse
from shared.persistence import repo

_log = structlog.get_logger(__name__)


class _BackgroundLoop:
    """A singleton asyncio loop on a daemon thread for sync->async DB writes.

    One process-wide loop is cheap and avoids spinning a thread per call. It is
    created lazily and lives for the process lifetime (daemon thread).
    """

    _instance: "_BackgroundLoop | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run, name="llm-persist-loop", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    @classmethod
    def instance(cls) -> "_BackgroundLoop":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def run_blocking(self, coro: Coroutine[Any, Any, None]) -> None:
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        fut.result()


def _to_text(raw: Mapping[str, object]) -> str | None:
    """Serialize a raw provider payload to JSON text (best-effort, never raises)."""
    if not raw:
        return None
    try:
        return json.dumps(raw, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(raw)


class PersistingLLMProvider:
    """``LLMProvider`` decorator that records each call to ``llm_calls``.

    Wrap a real provider; ``complete`` delegates to it, persists an ``llm_calls``
    row, then returns the inner response unchanged. Makes no extra model call.
    """

    def __init__(
        self,
        inner: LLMProvider,
        session_factory: async_sessionmaker[AsyncSession],
        run_id: str,
        pillar: str,
    ) -> None:
        self._inner = inner
        self._session_factory = session_factory
        self._run_id = run_id
        self._pillar = pillar

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        json_schema: Mapping[str, object] | None = None,
    ) -> LLMResponse:
        resp = self._inner.complete(
            prompt, system=system, max_tokens=max_tokens, json_schema=json_schema
        )
        self._record(prompt, system, resp)
        return resp

    def _record(self, prompt: str, system: str | None, resp: LLMResponse) -> None:
        async def _write() -> None:
            async with self._session_factory() as s:
                await repo.record_llm_call(
                    s,
                    run_id=self._run_id,
                    pillar=self._pillar,
                    model=resp.model,
                    prompt=prompt,
                    system=system,
                    raw_response=_to_text(resp.raw),
                    parsed_output=None,
                    input_tokens=resp.input_tokens,
                    output_tokens=resp.output_tokens,
                    dollars=resp.dollars,
                )

        try:
            _BackgroundLoop.instance().run_blocking(_write())
        except Exception as exc:  # pragma: no cover - defensive: never crash a run
            _log.warning(
                "llm_call.record_failed",
                pillar=self._pillar,
                run_id=self._run_id,
                error=f"{type(exc).__name__}: {exc}",
            )
