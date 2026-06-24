"""Metrics aggregator: the headline catch-rate numbers (US-14, US-10).

Computes the platform's verifier recall (catch rate) separately for the
black-box and white-box red passes, plus the gap between them. The white-box
pass hands the red agent the oracle scheme, so its catch rate is recall against
an informed attacker; the gap between black-box and white-box catch rate is the
report card (ARCHITECTURE.md section 3, "the catch-rate gap is the report card").

Catch rate is measured from real rows only: every verdict joined to its attack,
the attack's `white_box` flag picking the box. A box with zero judged attacks
reports rate `None`, which the dashboard renders as "Not yet measured" rather
than a misleading 0.0 (US-10). Nothing here samples or zero-defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.persistence.models import Attack as AttackRow
from shared.persistence.models import Verdict as VerdictRow


@dataclass(frozen=True, slots=True)
class CatchRate:
    """Verifier recall for one red pass (one box), over real verdicts only."""

    box: str
    judged: int
    caught: int
    rate: float | None
    latest_at: str | None

    def as_json(self) -> dict[str, Any]:
        return {
            "box": self.box,
            "judged": self.judged,
            "caught": self.caught,
            "undetected": self.judged - self.caught,
            "rate": self.rate,
            "latest_at": self.latest_at,
        }


@dataclass(frozen=True, slots=True)
class CatchRateMetrics:
    """Black-box and white-box catch rate side by side, with the gap (US-14)."""

    black_box: CatchRate
    white_box: CatchRate
    gap: float | None

    def as_json(self) -> dict[str, Any]:
        return {
            "black_box_catch_rate": self.black_box.as_json(),
            "white_box_catch_rate": self.white_box.as_json(),
            # The report card: how much catch rate is borrowed from attacker
            # ignorance. None until both boxes have at least one judged attack.
            "catch_rate_gap": self.gap,
        }


def _rate(caught: int, judged: int) -> float | None:
    """Catch rate as caught / judged, or None when nothing has been judged."""
    return (caught / judged) if judged else None


@dataclass(frozen=True, slots=True)
class MetricsAggregator:
    """Reads attacks and verdicts and computes the catch-rate metrics."""

    session: AsyncSession

    async def catch_rates(self) -> CatchRateMetrics:
        """Compute black-box and white-box catch rate from real verdicts.

        Joins every verdict to its attack so an attempt with no verdict (a
        malformed proposal the loop never submitted) is excluded from the
        denominator: catch rate is recall over judged submissions only. An
        attack is "caught" when it was not undetected, where the undetected
        signal is the loop's domain-appropriate one (the oracle verdict for a
        code target, the model's own query_target evasion for a scored model),
        persisted on ``attacks.succeeded`` so this read is target-agnostic.
        """
        stmt = select(AttackRow.white_box, AttackRow.succeeded, VerdictRow.created_at).join(
            VerdictRow, VerdictRow.attack_id == AttackRow.id
        )
        rows = (await self.session.execute(stmt)).all()

        buckets: dict[bool, list[tuple[bool, datetime]]] = {False: [], True: []}
        for white_box, undetected, created_at in rows:
            buckets[white_box].append((undetected, created_at))

        black = self._bucket("black_box", buckets[False])
        white = self._bucket("white_box", buckets[True])
        gap = (
            black.rate - white.rate
            if black.rate is not None and white.rate is not None
            else None
        )
        return CatchRateMetrics(black_box=black, white_box=white, gap=gap)

    @staticmethod
    def _bucket(box: str, rows: list[tuple[bool, datetime]]) -> CatchRate:
        judged = len(rows)
        caught = sum(1 for undetected, _ in rows if not undetected)
        latest = max((created_at for _, created_at in rows), default=None)
        return CatchRate(
            box=box,
            judged=judged,
            caught=caught,
            rate=_rate(caught, judged),
            latest_at=latest.isoformat() if latest is not None else None,
        )
