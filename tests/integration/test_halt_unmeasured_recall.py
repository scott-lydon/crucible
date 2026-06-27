"""Issue #5 (Gustavo / Measure lane) — FIXED: the halt rule now fails CLOSED on
unmeasured recall.

Previously ``modules/measure/halt.py`` certified off the most recent run whose
``white_box_recall`` was NOT NULL. A white-box pass that fully evades the held-out
oracle produces ``wb_wrong == 0``, so ``orchestrator/loop.py`` leaves recall NULL and
the gate silently skipped that run, certifying off an OLDER, healthier run — exactly
the run where the verifier was most defeated produced no halt.

``halt_state`` now reads the latest COMPLETED run regardless of recall: if recall has
ever been measured and the latest completed run cannot measure it, the platform refuses
to certify (fail closed). A history that never measured recall (e.g. only agent or
co-evolution runs with no white-box fraud pass) is treated as "not applicable" and does
not halt.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from modules.measure.halt import halt_state
from shared.persistence.models import Run
from tests.conftest import run_db

_EARLY = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
_LATE = dt.datetime(2026, 1, 2, tzinfo=dt.UTC)


def _run(run_id: str, created_at: dt.datetime, recall: float | None) -> Run:
    return Run(
        id=run_id, created_at=created_at, status="complete", target_kind="fraud",
        shape="shape1_ml", budget_rounds=5, budget_dollars=1.0, white_box_recall=recall,
    )


def test_unmeasured_latest_run_fails_closed() -> None:
    """When the latest completed run could not measure recall but an earlier run did,
    the gate halts rather than certifying off the stale healthier run."""

    async def work(session: AsyncSession) -> dict[str, Any]:
        session.add(_run("run-old-good", _EARLY, recall=0.95))   # older, healthy
        session.add(_run("run-new-evaded", _LATE, recall=None))  # latest, unmeasured
        await session.flush()
        return await halt_state(session)

    halt = run_db(work)
    assert halt["halted"] is True
    assert halt["white_box_recall"] is None          # reflects the latest run, not the stale one
    assert "evaded" in str(halt["message"]).lower()


def test_never_measured_recall_does_not_halt() -> None:
    """A history with no white-box recall ever measured (e.g. agent/co-evolution runs)
    is 'not applicable', not evasion — the gate stays open."""

    async def work(session: AsyncSession) -> dict[str, Any]:
        session.add(_run("run-agent-1", _EARLY, recall=None))
        session.add(_run("run-agent-2", _LATE, recall=None))
        await session.flush()
        return await halt_state(session)

    halt = run_db(work)
    assert halt["halted"] is False
