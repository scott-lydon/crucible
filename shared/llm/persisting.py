"""A persisting decorator for ``LLMProvider``.

``PersistingLLMProvider`` wraps any ``LLMProvider`` and writes one ``llm_calls``
row AROUND each ``complete(...)`` — capturing the prompt, system, raw response,
token counts, and dollar cost so the dashboard's Inspect button (US-2/US-3) has
real data and the dollars-per-caught-hack tile (US-10) can be computed. It is a
pure decorator: it makes NO extra model call, and returns the inner response
unchanged.

The seam is awkward: ``LLMProvider.complete`` is synchronous and is called from
inside the orchestrator's *running* async event loop (the oracle/adversary
``vote``/``mutate`` methods are invoked synchronously inside ``run_loop``). The
process-shared async engine is asyncpg, whose connections are PINNED to the loop
that created them (the uvicorn loop) — they cannot be reused from a foreign
loop/thread. So we MUST NOT touch the async engine from here.

Loop-safe fix (Option A): the write goes through a dedicated, blocking SYNC
SQLAlchemy engine built from the SAME DB URL (``postgresql+psycopg`` for the
Postgres runtime, plain ``sqlite`` for tests). No event loop is involved on the
write path, so there is no cross-loop hazard — ``complete()`` does one fast
blocking INSERT and returns. The sync engine is created once per distinct URL
and reused process-wide (a short-lived session per insert, no per-call connect).

Fail-loud-but-don't-crash: a persistence error is logged and swallowed so a
recording failure never aborts a run — but the call IS recorded on the happy
path (we never silently drop records on a healthy DB).
"""

import json
import threading
import uuid
from collections.abc import Mapping

import structlog
from sqlalchemy import Engine

from shared.llm.base import LLMProvider, LLMResponse
from shared.persistence import (make_sync_engine, make_sync_session_factory,
                                 sync_url)
from shared.persistence.models import LlmCallRow

_log = structlog.get_logger(__name__)

# One sync engine per distinct (sync) DB URL, reused process-wide. asyncpg's
# loop-pinning does not apply here — a sync engine has its own blocking driver
# and connection pool, safe to call from any thread/loop. Guarded so concurrent
# first-use does not build two engines for the same URL.
_engines: dict[str, Engine] = {}
_engines_lock = threading.Lock()


def _engine_for(db_url: str) -> Engine:
    key = sync_url(db_url)
    with _engines_lock:
        engine = _engines.get(key)
        if engine is None:
            engine = make_sync_engine(db_url)
            _engines[key] = engine
        return engine


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
    row via a loop-safe SYNC write, then returns the inner response unchanged.
    Makes no extra model call.

    ``db_url`` is the SAME DB URL the async engine uses (e.g.
    ``postgresql+asyncpg://...`` or ``sqlite+aiosqlite://...``); it is translated
    to its sync-driver equivalent for the blocking write. No async session
    factory is taken — the write deliberately never touches the async engine.
    """

    def __init__(
        self,
        inner: LLMProvider,
        db_url: str,
        run_id: str,
        pillar: str,
    ) -> None:
        self._inner = inner
        self._db_url = db_url
        self._run_id = run_id
        self._pillar = pillar
        self._session_factory = make_sync_session_factory(_engine_for(db_url))

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
        try:
            with self._session_factory() as s:
                s.add(
                    LlmCallRow(
                        id=str(uuid.uuid4()),
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
                )
                s.commit()
        except Exception as exc:  # pragma: no cover - defensive: never crash a run
            _log.warning(
                "llm_call.record_failed",
                pillar=self._pillar,
                run_id=self._run_id,
                error=f"{type(exc).__name__}: {exc}",
            )
