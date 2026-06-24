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

    @property
    def name(self) -> str:
        """The oracle's stable name, shown on its verdict card."""
        ...

    @property
    def weight(self) -> float:
        """Vote weight. Four oracles carry 1.0; the LLM judge carries 0.5 (US-4).

        Read-only so an oracle can be a frozen value object and still satisfy
        the Protocol (same pattern as Target.target_type).
        """
        ...

    @property
    def protocol_description(self) -> str:
        """One-line description of what this oracle checks and how.

        Disclosed to the red agent in the white-box pass (US-14), so the
        informed attacker knows which checks fire, what relations they verify,
        and how the held-out generator is structured. Owned by each oracle
        (Targets-and-Oracles), assembled into the red prompt by the loop.
        """
        ...

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
