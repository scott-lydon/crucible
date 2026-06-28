"""Halt-certification rule (spec US-13; PR3 port E1/E2/E3).

The platform refuses to certify what its verifier cannot defend. The halt decision is:

- E3 (trust-gated): halt when ``(1 - silent_failure_rate) < threshold`` — i.e. Julian's
  trust score is below the red line. This is the headline gate: it keys on silent failures
  (held-out-confirmed wrongness the panel missed), NOT raw catch rate, so a producer that
  is "caught a lot" but still leaks silently is not certified.
- Preserved from PR #5 (fail-closed): also halt when the latest completed run could not
  MEASURE white-box recall (ground truth may have been fully evaded) — refusing to certify
  off an earlier, healthier run. The two conditions are OR'd; either halts.

E1 (persisted): the decision is written to a small state file with a ``last_evaluated``
timestamp that only advances when the decision CHANGES, so a page refresh shows a stable
timestamp (the banner reads from the persisted row, not a fresh clock each load).

E2 (override): a devmode bypass lets the operator launch a new run despite a halt for
manual testing; it never changes the displayed metric — the banner keeps reporting the
real halt.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.measure.trust import compute_trust
from shared.config import load_settings
from shared.persistence.models import Run

_STATE_FILE = Path(__file__).resolve().parents[2] / "artifacts" / "halt-state.json"

# E2: devmode launch override (in memory, defaults OFF so the spec'd 409 holds unless
# explicitly armed). It bypasses the launch guard only; the banner keeps reporting the halt.
_launch_override = False


def set_halt_override(value: bool) -> None:
    """Arm/disarm the devmode bypass of the halt launch guard (E2)."""
    global _launch_override
    _launch_override = value


def get_halt_override() -> bool:
    """Whether the devmode halt bypass is currently armed."""
    return _launch_override


def _read_state() -> dict[str, Any]:
    if not _STATE_FILE.exists():
        return {}
    try:
        result: dict[str, Any] = json.loads(_STATE_FILE.read_text("utf-8"))
        return result
    except (ValueError, OSError):
        return {}


def _write_state(state: dict[str, Any]) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state), encoding="utf-8")


async def _recall_state(session: AsyncSession, threshold: float) -> tuple[float | None, bool, bool]:
    """The latest completed run's white-box recall, and the two PR #5/#7 recall gates:
    (recall, recall_below_threshold, fail_closed_on_unmeasured)."""
    latest = (
        await session.execute(
            select(Run).where(Run.status == "complete").order_by(Run.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if latest is None:
        return None, False, False
    recall = float(latest.white_box_recall) if latest.white_box_recall is not None else None
    if recall is not None:
        return recall, recall < threshold, False
    measured_ever = (
        await session.execute(select(Run.id).where(Run.white_box_recall.is_not(None)).limit(1))
    ).first() is not None
    return None, False, measured_ever


async def _latest_completed_run_id(session: AsyncSession) -> str | None:
    latest = (
        await session.execute(
            select(Run.id).where(Run.status == "complete").order_by(Run.created_at.desc()).limit(1)
        )
    ).first()
    return None if latest is None else str(latest[0])


async def halt_state(session: AsyncSession) -> dict[str, object]:
    threshold = load_settings().halt_recall_threshold
    # Trust for the LATEST completed run (the run being certified), so a fresh leaky run is
    # not diluted by prior healthy history — consistent with the recall gate, which also
    # keys on the latest run.
    latest_run_id = await _latest_completed_run_id(session)
    trust = await compute_trust(session, run_id=latest_run_id)
    sfr = trust.get("silent_failure_rate")
    trust_score = trust.get("trust_score")

    # E3 (headline): halt on Julian's trust score (silent-failure rate), not raw catch rate.
    trust_halt = sfr is not None and (1.0 - float(sfr)) < threshold
    # Preserved recall gates (PR #5 fail-closed + PR #7 recall-below-threshold).
    recall, recall_below, recall_fail_closed = await _recall_state(session, threshold)
    halted = bool(trust_halt or recall_below or recall_fail_closed)

    if recall_below:
        message = f"Certification halted: recall is {recall:.2f}, threshold is {threshold:.2f}"
    elif recall_fail_closed:
        message = (
            "Certification halted: the latest completed run could not measure white-box "
            "recall (ground truth may have been evaded); refusing to certify off an "
            "earlier run."
        )
    elif trust_halt:
        message = (
            f"Halted: silent failure rate above threshold (trust {trust_score}/100 is below "
            f"{round(threshold * 100)})"
        )
    else:
        message = ""

    # E1: advance last_evaluated only when the decision changes, so a refresh is stable.
    signature = [halted, trust_score, recall, threshold]
    prev = _read_state()
    last_evaluated: str | None
    if prev.get("signature") != signature:
        last_evaluated = dt.datetime.now(dt.UTC).isoformat()
        _write_state({"signature": signature, "last_evaluated": last_evaluated})
    else:
        last_evaluated = prev.get("last_evaluated")

    return {
        "halted": halted,
        "trust_score": trust_score,
        "silent_failure_rate": sfr,
        "white_box_recall": recall,
        "threshold": threshold,
        "message": message,
        "last_evaluated": last_evaluated,
        "override": _launch_override,
    }
