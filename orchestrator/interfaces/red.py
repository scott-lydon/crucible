"""The Red port. The red agent reasons about why the last attack was caught and
proposes the next adversarial input (plan.md section 3 Pillar 2). The same agent
runs the black-box and the white-box pass (constitution.md section 3)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from shared.types.core import Attack, Verdict
from shared.types.ids import RunId
from shared.types.results import HealthStatus
from shared.types.sealed_spec import SealedSpec

# Loads the strategy catalog's most evasive prior-run tactics for a target kind, so the
# loop can prime a Primable red at run start (cr-b2). Injected through wiring.
TacticLoader = Callable[[AsyncSession, str], Awaitable[list[str]]]


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


@runtime_checkable
class Primable(Protocol):
    """A red agent that can be seeded with prior-run tactics before a run (cr-b2)."""

    def prime(self, known_tactics: Sequence[str]) -> None: ...


@runtime_checkable
class SchemeAware(Protocol):
    """A red agent that can be told which checkers are in the verification panel, so its
    white-box pass tries to beat the actual ensemble, not a guess (cr-b3)."""

    def note_scheme(self, scheme: str) -> None: ...
