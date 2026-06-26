"""Admin/leaderboard aggregations (cr-e4). Read-only summaries over the persisted run
data for the leaderboard and admin/debug dashboard screens. Pure measure-side queries —
no business logic, no producer access."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.persistence.models import (
    AgentConfigRow,
    AttackRow,
    CoevolutionRoundRow,
    LLMCallRow,
    Run,
    VerdictRow,
)


async def leaderboard(session: AsyncSession, *, limit: int = 100) -> list[dict[str, Any]]:
    """Per-run scoreboard, leakiest first. For a co-evolution run the final round's ASR
    (the agent's residual failure rate) ranks it; for a red-team run, the share of attacks
    the panel caught. Higher ASR / lower white-box recall = more at-risk."""
    runs = (
        await session.execute(select(Run).order_by(Run.created_at.desc()).limit(limit))
    ).scalars().all()
    names: dict[str, str] = {}
    for cfg in (await session.execute(select(AgentConfigRow))).scalars().all():
        names[cfg.id] = cfg.name

    rows: list[dict[str, Any]] = []
    for run in runs:
        final_asr: float | None = None
        final_detection: float | None = None
        n_rounds = 0
        coevo = (
            await session.execute(
                select(CoevolutionRoundRow)
                .where(CoevolutionRoundRow.run_id == run.id)
                .order_by(CoevolutionRoundRow.round_index.desc()))
        ).scalars().all()
        if coevo:
            n_rounds = len(coevo)
            final_asr = coevo[0].asr
            final_detection = coevo[0].detection
        rows.append({
            "runId": run.id,
            "agent": names.get(run.agent_config_id or "", run.target_kind),
            "target_kind": run.target_kind,
            "status": run.status,
            "white_box_recall": run.white_box_recall,
            "final_asr": final_asr,
            "final_detection": final_detection,
            "n_rounds": n_rounds,
            "created_at": run.created_at.isoformat(),
        })
    # Leakiest first: known ASR descending, then unknown ASR, then lowest white-box recall.
    rows.sort(key=lambda r: (
        r["final_asr"] if r["final_asr"] is not None else -1.0,
        -(r["white_box_recall"] if r["white_box_recall"] is not None else 1.0),
    ), reverse=True)
    return rows


async def debug_summary(session: AsyncSession) -> dict[str, Any]:
    """System state for the admin/debug screen: run counts by status, totals, spend."""
    status_counts: dict[str, int] = {}
    for status, count in (
        await session.execute(select(Run.status, func.count()).group_by(Run.status))
    ).all():
        status_counts[str(status)] = int(count)

    async def _count(model: Any) -> int:
        return int((await session.execute(select(func.count()).select_from(model))).scalar_one())

    dollars_q = select(func.coalesce(func.sum(LLMCallRow.dollars), 0.0))
    total_dollars = float((await session.execute(dollars_q)).scalar_one())
    errors = (
        await session.execute(
            select(Run.id, Run.error).where(Run.error.is_not(None))
            .order_by(Run.created_at.desc()).limit(10))
    ).all()
    return {
        "runs_by_status": status_counts,
        "totals": {
            "runs": sum(status_counts.values()),
            "attacks": await _count(AttackRow),
            "verdicts": await _count(VerdictRow),
            "llm_calls": await _count(LLMCallRow),
            "agent_configs": await _count(AgentConfigRow),
            "coevolution_rounds": await _count(CoevolutionRoundRow),
        },
        "llm_dollars_total": round(total_dollars, 6),
        "recent_errors": [{"runId": rid, "error": err} for rid, err in errors],
    }
