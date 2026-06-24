"""Corpus exporter: the seeded-hack benchmark as JSONL (US-11).

Streams every attack that got past the oracle ensemble (a successful, undetected
hack) with its full audit trace, so the benchmark outlives the demo. The export
is a stream, not a buffered list, so a large corpus does not have to fit in
memory; the row count of the download equals the row count of the table exactly
because both read the same query.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.persistence.models import Attack as AttackRow
from shared.persistence.models import Run


@dataclass(frozen=True, slots=True)
class CorpusExporter:
    """Reads and streams the successful-attack corpus over one session."""

    session: AsyncSession

    def _base_query(self) -> Any:
        """Successful attacks joined to their run's target type, oldest first.

        Ordered by creation so the export is stable across calls (the row count
        equality the done-criterion checks needs a deterministic set, and a
        researcher diffing two exports wants a stable order).
        """
        return (
            select(
                AttackRow.id,
                AttackRow.tactic,
                AttackRow.payload,
                AttackRow.audit_trace,
                AttackRow.dollars_spent,
                AttackRow.created_at,
                Run.target_type,
            )
            .join(Run, Run.id == AttackRow.run_id)
            .where(AttackRow.succeeded.is_(True))
            .order_by(AttackRow.created_at.asc())
        )

    async def count(self) -> int:
        """How many successful attacks the corpus holds (the table row count)."""
        total = (
            await self.session.execute(
                select(func.count())
                .select_from(AttackRow)
                .where(AttackRow.succeeded.is_(True))
            )
        ).scalar_one()
        return int(total)

    async def rows(self) -> list[dict[str, Any]]:
        """The corpus as a list of records for the `/corpus` table view."""
        result = await self.session.execute(self._base_query())
        return [self._record(row) for row in result.all()]

    async def stream_jsonl(self) -> AsyncIterator[str]:
        """Yield one JSON line per successful attack (US-11 download)."""
        result = await self.session.stream(self._base_query())
        async for row in result:
            yield json.dumps(self._record(row), sort_keys=True) + "\n"

    @staticmethod
    def _record(row: Any) -> dict[str, Any]:
        """One corpus record in the US-11 shape."""
        return {
            "attack_id": row.id,
            "target_type": row.target_type,
            "tactic": row.tactic,
            "prompt": row.payload,
            "audit_trace": row.audit_trace,
            "dollars": str(row.dollars_spent),
            "captured_at": row.created_at.isoformat(),
        }
