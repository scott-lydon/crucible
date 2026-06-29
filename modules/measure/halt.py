"""Halt-certification rule (spec US-13). When white-box verifier recall drops below
the configured red line, the platform refuses to issue new clean verdicts: the
orchestrator returns HTTP 409 on new run-launch requests and a red banner shows on
every dashboard route. Capability-threshold gating — the platform does not certify
what it cannot defend (plan.md section 5, Responsible Scaling spirit)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import load_settings
from shared.persistence.models import Run


async def halt_state(session: AsyncSession) -> dict[str, object]:
    threshold = load_settings().halt_recall_threshold
    # A threshold of 0 (or less) fully DISABLES the gate — an explicit kill-switch
    # (CRUCIBLE_HALT_RECALL=0) for demos / instances that don't want fail-closed
    # certification. It short-circuits BOTH halt paths (low recall AND unmeasurable recall),
    # so it can never block a launch. Any positive threshold keeps the full gate behaviour.
    if threshold <= 0:
        return {"halted": False, "white_box_recall": None, "threshold": threshold,
                "message": ""}
    # Read the latest COMPLETED run, not the latest run that happens to carry a recall.
    # Skipping NULL-recall runs (the old behaviour) let a run that fully evaded ground
    # truth — leaving white_box_recall NULL — be ignored, certifying off a stale healthier
    # run (issue #5). We now look at the latest completed run regardless of recall.
    latest = (
        await session.execute(
            select(Run)
            .where(Run.status == "complete")
            .order_by(Run.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    # Has white-box recall ever been measured? If not, no fraud white-box pass has run
    # (e.g. only agent/co-evolution runs), so an unmeasured run is "not applicable" rather
    # than evasion — do not halt on it.
    measured_ever = (
        await session.execute(
            select(Run.id).where(Run.white_box_recall.is_not(None)).limit(1)
        )
    ).first() is not None

    recall = (
        float(latest.white_box_recall)
        if latest is not None and latest.white_box_recall is not None
        else None
    )

    if latest is None:
        halted, message = False, ""
    elif recall is None:
        # Fail closed: the latest completed run could not measure recall. If recall has
        # ever been measured, the platform has lost the ability to verify (e.g. the
        # attacker fully evaded ground truth) — refuse to certify off an earlier run.
        halted = measured_ever
        message = (
            "Not certified: the latest completed run could not measure white-box recall "
            "(ground truth may have been evaded). Advisory only — the platform stays usable."
            if halted else ""
        )
    else:
        halted = recall < threshold
        message = (
            f"Not certified: white-box recall is {recall:.2f}, below the {threshold:.2f} line. "
            f"Advisory only — the platform stays usable."
            if halted else ""
        )
    return {"halted": halted, "white_box_recall": recall, "threshold": threshold,
            "message": message}
