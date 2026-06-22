"""Server-side sealed-spec resolver. Oracles read the spec through this function,
which runs in the orchestrator process (it holds the Postgres credentials). The
producer container cannot call it: it has no database credentials and no network
(the local sandbox seal), so the sealed spec is unreachable from inside the
producer (constitution.md section 3).

Takes the caller's session so it composes inside the loop's one-transaction-per-emit
unit of work (plan.md section 4)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.persistence.models import SpecRow
from shared.types.sealed_spec import SealedSpec


async def resolve_spec(session: AsyncSession, run_id: str) -> SealedSpec:
    row = (
        await session.execute(select(SpecRow).where(SpecRow.run_id == run_id))
    ).scalar_one()
    return SealedSpec.from_dict(row.payload)
