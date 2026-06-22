"""The Oracle port. Each of the five verifiers implements this. An oracle votes on
whether one producer output violates the sealed spec; it never sees the other
oracles' votes (non-colluding ensemble, plan.md section 5)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from shared.types.core import Attack, OracleVote, Verdict
from shared.types.enums import OracleKind
from shared.types.results import HealthStatus
from shared.types.sealed_spec import SealedSpec


@runtime_checkable
class Oracle(Protocol):
    kind: OracleKind
    weight: float   # 1.0 for the four independent oracles, 0.5 for the LLM judge

    async def vote(
        self, spec: SealedSpec, attack: Attack, output: Mapping[str, Any]
    ) -> OracleVote:
        """Check one producer output against the spec and return a reasoned vote."""
        ...

    async def health(self) -> HealthStatus: ...


class VerifyFn(Protocol):
    """The aggregator, injected into the loop by wiring so loop.py never imports a
    concrete module (constitution.md section 2). Polls the oracles and aggregates."""

    async def __call__(
        self,
        oracles: Sequence[Oracle],
        spec: SealedSpec,
        attack: Attack,
        output: Mapping[str, Any],
    ) -> Verdict: ...
