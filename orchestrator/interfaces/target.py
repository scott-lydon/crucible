"""Target port.

A target is the system under test. Adapters wrap a Shape 1 model (the fraud
LightGBM classifier) or a Shape 2 agent (the code agent) behind this one
Protocol, so the orchestrator core never changes when the target does
(ARCHITECTURE.md section 3, "target-agnostic").
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from shared.types import ProbeResult, SealedSpec, TargetOutput, TargetType


@runtime_checkable
class Target(Protocol):
    """The system under test."""

    target_type: TargetType

    async def submit(self, spec: SealedSpec, attack_input: dict[str, Any]) -> TargetOutput:
        """Run the target on one input and return its output plus a producer audit."""
        ...

    async def query_target(self, attack_input: dict[str, Any]) -> float:
        """Return the target's own numeric signal for one input.

        This is the first-class tool the red agent calls to probe the target
        (the fraud probability, for example) while searching for an evasion.
        """
        ...

    async def self_test(self) -> ProbeResult:
        """Run the subcomponent smoke test for the /health page (US-8)."""
        ...
