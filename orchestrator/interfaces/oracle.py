"""Oracle port.

An oracle checks a submission against the sealed spec without trusting the
producer. Four oracles plus one judge implement this Protocol, each failing
differently so a hack that slips past one is caught by another
(ARCHITECTURE.md section 3).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from shared.types import OracleVote, ProbeResult, SealedSpec, TargetOutput


@runtime_checkable
class Oracle(Protocol):
    """One non-colluding check over a submission."""

    name: str
    # Four oracles carry weight 1.0; the LLM judge carries 0.5 (US-4).
    weight: float

    async def verify(
        self,
        spec: SealedSpec,
        attack_input: dict[str, Any],
        output: TargetOutput,
    ) -> OracleVote:
        """Return this oracle's vote with its reasoning attached."""
        ...

    async def self_test(self) -> ProbeResult:
        """Run the subcomponent smoke test for the /health page (US-8)."""
        ...
