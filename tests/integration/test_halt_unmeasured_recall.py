"""Verification finding #2 (Gustavo / Measure lane): the halt-certification rule fails
OPEN on unmeasured recall.

``modules/measure/halt.py`` certifies/halts off the most recent run whose
``white_box_recall`` is NOT NULL (``.where(Run.white_box_recall.is_not(None))``). But a
white-box pass that fully evades the held-out oracle produces ``wb_wrong == 0``, so
``orchestrator/loop.py`` never sets ``white_box_recall`` and the column stays NULL
(see Finding #1). The gate then silently skips that run and keeps certifying off an
OLDER, healthier run — exactly the run where the verifier was most defeated produces
no halt and no number. That is fail-open behaviour; the Responsible-Scaling spirit the
halt.py docstring invokes wants fail-closed: do not certify what you cannot measure.

These tests drive the real ``halt_state``. The first characterises today's fail-open
behaviour (passes); the second asserts the fail-closed property and is a strict xfail —
flip it to a code change and it becomes XPASS, forcing the marker's removal.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.measure.halt import halt_state
from shared.persistence.models import Run
from tests.conftest import run_db

_EARLY = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
_LATE = dt.datetime(2026, 1, 2, tzinfo=dt.timezone.utc)


def _run(run_id: str, created_at: dt.datetime, recall: float | None) -> Run:
    return Run(
        id=run_id, created_at=created_at, status="complete", target_kind="fraud",
        shape="shape1_ml", budget_rounds=5, budget_dollars=1.0, white_box_recall=recall,
    )


def test_unmeasured_latest_run_certifies_off_stale_run() -> None:
    """Characterisation: the most recent run has unmeasured (NULL) recall — the verifier
    was fully evaded — yet halt_state reports healthy certification using an older run."""

    async def work(session: AsyncSession) -> dict:
        session.add(_run("run-old-good", _EARLY, recall=0.95))   # older, healthy
        session.add(_run("run-new-evaded", _LATE, recall=None))  # latest, unmeasured
        await session.flush()
        return await halt_state(session)

    halt = run_db(work)
    # The dangerous latest run is invisible; the gate trusts the stale 0.95.
    assert halt["halted"] is False
    assert halt["white_box_recall"] == pytest.approx(0.95)


@pytest.mark.xfail(
    strict=True,
    reason="Finding #2: halt rule fails OPEN when the most recent run's white-box "
    "recall is unmeasured (NULL after full ground-truth evasion). Responsible-Scaling "
    "spirit wants fail-closed: an unmeasured latest run must not certify off a stale "
    "healthier run. Design decision for the engine owner.",
)
def test_unmeasured_latest_run_must_not_certify() -> None:
    """Desired property: when the most recent completed run could not measure white-box
    recall, the platform must not keep certifying off an older run — it should halt
    (fail closed)."""

    async def work(session: AsyncSession) -> dict:
        session.add(_run("run-old-good", _EARLY, recall=0.95))
        session.add(_run("run-new-evaded", _LATE, recall=None))
        await session.flush()
        return await halt_state(session)

    halt = run_db(work)
    assert halt["halted"] is True, (
        "unmeasured latest recall should fail closed, not certify off a stale run"
    )
