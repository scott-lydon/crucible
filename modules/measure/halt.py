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
    row = (
        await session.execute(
            select(Run)
            .where(Run.white_box_recall.is_not(None))
            .order_by(Run.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    recall = (
        float(row.white_box_recall)
        if row is not None and row.white_box_recall is not None
        else None
    )
    halted = recall is not None and recall < threshold
    message = (
        f"Certification halted: recall is {recall:.2f}, threshold is {threshold:.2f}"
        if halted and recall is not None
        else ""
    )
    return {"halted": halted, "white_box_recall": recall, "threshold": threshold,
            "message": message}
