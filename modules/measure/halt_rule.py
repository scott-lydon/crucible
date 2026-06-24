"""Halt certification at a residual red line (US-13 / slice-18).

The verifier recall on the white-box self-test is the persisted
``white_box_catch_rate`` (the fraction of an INFORMED attacker's successful
evasions the oracles still caught). When that recall drops BELOW a configured
threshold (default 0.7, override via ``CRUCIBLE_HALT_RECALL_THRESHOLD``), the
platform is HALTED: it refuses to issue new clean verdicts, so the orchestrator
refuses new run launches.

The halt flag is persisted (``HaltStateRow``) so it survives restarts. The
recall used here is the LATEST white-box pass's recall. If no white-box metric
has been recorded yet, recall is genuinely UNDEFINED (``None``) and the platform
is NOT halted — we never fabricate a 0.0 to trip the red line.
"""

import os
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.persistence import repo
from shared.persistence.models import WhiteBoxMetricsRow

DEFAULT_HALT_RECALL_THRESHOLD = 0.7
_THRESHOLD_ENV = "CRUCIBLE_HALT_RECALL_THRESHOLD"


@dataclass(frozen=True, slots=True)
class HaltStatus:
    """The certification halt verdict the dashboard banner + 409 body read from."""

    halted: bool
    recall: float | None
    threshold: float

    def to_dict(self) -> dict[str, object]:
        return {"halted": self.halted, "recall": self.recall, "threshold": self.threshold}


def halt_recall_threshold() -> float:
    """The configured red line: ``CRUCIBLE_HALT_RECALL_THRESHOLD`` or 0.7.

    A malformed env value falls back to the default rather than crashing the
    launch path (validated at this system boundary).
    """
    raw = os.environ.get(_THRESHOLD_ENV)
    if raw is None:
        return DEFAULT_HALT_RECALL_THRESHOLD
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_HALT_RECALL_THRESHOLD


async def _latest_white_box_recall(s: AsyncSession) -> tuple[float | None, str | None]:
    """The most-recent white-box recall + its source run id (None if unmeasured)."""
    res = await s.execute(
        select(WhiteBoxMetricsRow).order_by(WhiteBoxMetricsRow.created_at.desc())
    )
    row = res.scalars().first()
    if row is None:
        return None, None
    return row.white_box_catch_rate, row.run_id


async def evaluate_halt(s: AsyncSession) -> HaltStatus:
    """Recompute the halt verdict from the LATEST white-box recall and persist it.

    Halted iff a recall HAS been measured and it is strictly below the threshold.
    No white-box metric yet => recall ``None`` => NOT halted (undefined, never a
    fabricated 0). Writes the result to the persisted singleton so it survives
    restarts, then returns it.
    """
    threshold = halt_recall_threshold()
    recall, source_run_id = await _latest_white_box_recall(s)
    halted = recall is not None and recall < threshold
    await repo.set_halt_state(
        s,
        halted=halted,
        recall=recall,
        threshold=threshold,
        source_run_id=source_run_id,
    )
    return HaltStatus(halted=halted, recall=recall, threshold=threshold)


async def halt_status(s: AsyncSession) -> HaltStatus:
    """The current halt status the dashboard banner reads.

    Reads the PERSISTED flag if present (so a halt survives restarts even before
    the next white-box pass); otherwise evaluates fresh from white-box metrics.
    """
    row = await repo.get_halt_state(s)
    if row is None:
        return await evaluate_halt(s)
    threshold = row.threshold if row.threshold is not None else halt_recall_threshold()
    return HaltStatus(halted=row.halted, recall=row.recall, threshold=threshold)
