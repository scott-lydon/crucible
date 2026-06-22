"""The Blue port. Reads the strategy catalog, proposes a hardening patch, applies
it (a LightGBM retrain for Shape 1, a prompt-and-config diff for Shape 2), and
validates on a held-out attack set it never trained on (plan.md section 3 Pillar 3,
spec US-7)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from shared.types.core import Attack
from shared.types.ids import RunId
from shared.types.results import HealthStatus, PatchResult
from shared.types.sealed_spec import SealedSpec


@runtime_checkable
class BlueAgent(Protocol):
    async def harden(
        self,
        spec: SealedSpec,
        run_id: RunId,
        catalog_slice: Sequence[Attack],
    ) -> PatchResult:
        """Propose + apply + held-out-validate one hardening patch."""
        ...

    async def health(self) -> HealthStatus: ...
