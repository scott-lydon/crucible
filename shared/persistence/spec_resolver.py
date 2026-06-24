"""Server-side resolver for sealed specs.

Oracles read the sealed spec through this resolver. The producer runs in the
sealed sandbox with no network, so it cannot reach Postgres and therefore
cannot read a spec through any path. This is the read side of the core bet:
the spec is available to the checks, never to the thing being checked.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from shared.persistence.models import Spec
from shared.types import CrucibleError, SealedSpec, SpecId


class SpecNotFoundError(CrucibleError):
    """A spec id was resolved that is not present in the specs table."""


@dataclass(frozen=True, slots=True)
class SpecResolver:
    """Reads and writes sealed specs server-side, on a caller-provided session."""

    session: AsyncSession

    async def save(self, spec: SealedSpec) -> None:
        """Persist a sealed spec so oracles can resolve it later."""
        self.session.add(Spec(id=spec.spec_id.value, spec_json=spec.as_json()))
        await self.session.flush()

    async def get(self, spec_id: SpecId) -> SealedSpec:
        """Return the sealed spec for an id, or raise a typed, named error."""
        row = await self.session.get(Spec, spec_id.value)
        if row is None:
            raise SpecNotFoundError(
                f"No sealed spec with id {spec_id.value!r} in the specs table. "
                f"It must be sealed via SpecResolver.save before an oracle resolves it."
            )
        return SealedSpec.from_stored(row.spec_json)
