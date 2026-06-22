"""The Red port. The red agent reasons about why the last attack was caught and
proposes the next adversarial input (plan.md section 3 Pillar 2). The same agent
runs the black-box and the white-box pass (constitution.md section 3)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from shared.types.core import Attack, Verdict
from shared.types.ids import RunId
from shared.types.results import HealthStatus
from shared.types.sealed_spec import SealedSpec


@runtime_checkable
class RedAgent(Protocol):
    async def propose(
        self,
        spec: SealedSpec,
        run_id: RunId,
        round_index: int,
        last_verdict: Verdict | None,
        white_box: bool,
    ) -> Attack:
        """Propose the next attack. ``last_verdict`` is the feedback to reason from;
        ``white_box`` injects the oracles' protocol descriptions into the prompt."""
        ...

    async def health(self) -> HealthStatus: ...
