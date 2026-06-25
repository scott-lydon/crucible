"""Out-of-process run worker: ``python -m orchestrator.worker <run_id>``.

Spawned by ``orchestrator.api.create_run`` to drive a campaign to completion in
its OWN process so the heavy, largely-synchronous work (blocking Anthropic
``complete()`` HTTP calls, LightGBM training, the Docker sandbox subprocess)
NEVER runs on the API's single event loop — the API stays responsive (page
fetches + the SSE poller keep ticking) for the whole run.

Why a subprocess and not a thread: its own process means its own event loop and
its own asyncpg connections, so no async engine is ever shared across loops —
deliberately sidestepping the cross-loop asyncpg hazard hit in
``PersistingLLMProvider``.

Contract:
  * Reads the run's persisted ``params_json`` (written by ``create_run``) and
    reconstructs the ``LaunchRequest``, then drives the SAME ``_execute_run``
    path as the inline test dispatch — byte-for-byte identical build/seal/run.
  * On ANY exception it marks the run ``failed`` with the error (a superset of
    the loop's own failure capture, covering errors raised before the loop too),
    so the dashboard always shows an honest terminal status — never a run stuck
    forever in ``running`` because its worker died.
  * Exits non-zero on failure so a supervisor can see it; the API does not await
    the child, so this is purely for operability.

Only spawned when the active DB is reachable from a separate process (Postgres
or file-backed SQLite); an in-memory SQLite run executes inline in the API and
never reaches here.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys

from orchestrator.api import execute_run_by_id
from orchestrator.db import init_db, session_factory
from shared.env import load_env
from shared.persistence import repo


async def _run(run_id: str) -> None:
    """Initialize this process's own DB engine, then drive the run to completion.

    ``init_db`` resolves the SAME database URL the API uses (``CRUCIBLE_DATABASE_URL``
    env / the Postgres default) and builds a fresh async engine bound to THIS
    process's loop. ``create_all`` is idempotent (skips existing tables), so it is
    safe to call against the already-migrated prod schema.

    A SIGTERM (the stop endpoint's prompt-kill of the worker) cancels the run
    task; we catch ``CancelledError`` and finalize an honest terminal status —
    ``stopped`` if a cancel was requested, else ``failed`` — so a hard kill never
    leaves the run stuck in ``running``/``stopping``.
    """
    load_env()
    await init_db()
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    if task is not None:
        with contextlib.suppress(NotImplementedError):  # Windows has no SIGTERM
            loop.add_signal_handler(signal.SIGTERM, task.cancel)
    try:
        await execute_run_by_id(run_id)
    except asyncio.CancelledError:
        # SIGTERM from a stop request: finalize to the cooperative terminal status.
        await _finalize_cancelled(run_id)
        raise
    except Exception as exc:  # noqa: BLE001 — last-resort honest failure capture
        await _finalize_failed(run_id, exc)
        raise


async def _finalize_cancelled(run_id: str) -> None:
    """Stamp a hard-killed run terminal: ``stopped`` if a cancel was requested.

    The stop endpoint sets ``cancel_requested`` BEFORE terminating the worker, so
    by the time SIGTERM lands the flag is durable — we honor it as ``stopped``. If
    (defensively) no cancel was flagged, treat the abrupt kill as ``failed``.
    Idempotent: a run already at a terminal status is left untouched.
    """
    try:
        async with session_factory()() as s:
            run = await repo.get_run(s, run_id)
            if run is not None and run.status not in repo.TERMINAL_STATUSES:
                run.status = "stopped" if run.cancel_requested else "failed"
                if run.status == "failed":
                    run.error = "worker terminated"
                await s.commit()
    except Exception:  # noqa: BLE001 — never mask the cancellation
        pass


async def _finalize_failed(run_id: str, exc: BaseException) -> None:
    """Best-effort: stamp the run ``failed`` with the error so the UI is honest.

    The loop already marks failures it owns; this covers anything raised OUTSIDE
    the loop (component build, spec seal) and is idempotent if the loop got there
    first. Swallows secondary errors so the original exception is what surfaces.
    """
    try:
        async with session_factory()() as s:
            run = await repo.get_run(s, run_id)
            if run is not None and run.status not in repo.TERMINAL_STATUSES:
                run.status = "failed"
                run.error = f"{type(exc).__name__}: {exc}"
                await s.commit()
    except Exception:  # noqa: BLE001 — never mask the real failure
        pass


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m orchestrator.worker <run_id>", file=sys.stderr)
        return 2
    run_id = args[0]
    try:
        asyncio.run(_run(run_id))
    except (Exception, asyncio.CancelledError) as exc:  # noqa: BLE001
        print(f"worker stopped for run {run_id}: {exc!r}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
