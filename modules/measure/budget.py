"""Real-LLM cost meter + budget cap (cr-f4). Every Anthropic call's real cost is already
persisted on ``llm_calls`` (cr-b4); this module sums it per-run and globally, and decides
when a run must stop. Two ceilings: a per-run cap (the operator's AttackBudget) and a
global cap (config ``CRUCIBLE_GLOBAL_BUDGET``) that protects the shared key on a public
endpoint. This is the HARD prerequisite for enabling real Claude (cr-f5): without it a
public run could spend without bound."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.persistence.models import LLMCallRow


async def run_spend(session: AsyncSession, run_id: str) -> float:
    q = select(func.coalesce(func.sum(LLMCallRow.dollars), 0.0)).where(
        LLMCallRow.run_id == run_id)
    return float((await session.execute(q)).scalar_one())


async def global_spend(session: AsyncSession) -> float:
    q = select(func.coalesce(func.sum(LLMCallRow.dollars), 0.0))
    return float((await session.execute(q)).scalar_one())


def should_halt(
    run_spent: float, per_run_cap: float, global_spent: float, global_cap: float
) -> str | None:
    """The reason to stop, or None to continue. A cap of 0 (or less) is treated as 'no
    explicit cap' for the per-run case, but the global cap always applies."""
    if per_run_cap > 0 and run_spent >= per_run_cap:
        return (f"per-run budget reached: spent ${run_spent:.4f} of ${per_run_cap:.2f}")
    if global_cap > 0 and global_spent >= global_cap:
        return (f"global budget reached: spent ${global_spent:.4f} of ${global_cap:.2f}")
    return None


async def budget_status(
    session: AsyncSession, *, run_id: str | None, per_run_cap: float, global_cap: float
) -> dict[str, Any]:
    g = await global_spend(session)
    r = await run_spend(session, run_id) if run_id is not None else None
    return {
        "global_spent": round(g, 6),
        "global_cap": global_cap,
        "global_remaining": round(max(0.0, global_cap - g), 6),
        "global_exceeded": global_cap > 0 and g >= global_cap,
        "run_spent": None if r is None else round(r, 6),
        "per_run_cap": per_run_cap,
        "run_exceeded": r is not None and per_run_cap > 0 and r >= per_run_cap,
    }
