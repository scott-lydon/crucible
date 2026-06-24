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

    @property
    def target_type(self) -> TargetType:
        """Which target type this adapter implements (immutable identity).

        Declared read-only so both a plain class attribute (DummyTarget) and a
        frozen dataclass field (CodeAgentTarget and later targets) satisfy it.
        """
        ...

    @property
    def display_name(self) -> str:
        """Human-readable name shown on the dashboard's target picker.

        Owned by the adapter, not a separate catalog, because the adapter is
        the source of truth for its own identity. Read-only so a plain class
        attribute or a frozen dataclass field both satisfy the Protocol.
        """
        ...

    @property
    def description(self) -> str:
        """One-line tagline shown on the dashboard's target card.

        Same ownership and read-only reasoning as ``display_name``.
        """
        ...

    @property
    def artifact_ref(self) -> str:
        """Stable identity string for the deployed artifact and its version.

        Format ``<adapter>@<version>``, where ``<version>`` is a short stable
        identifier (model file sha for Shape 1 targets, code-config sha for
        Shape 2). The launcher renders this verbatim so the operator can see
        exactly which artifact a run is being launched against.
        """
        ...

    @property
    def oracle_verified(self) -> bool:
        """Whether the independent oracle ensemble decides this target's verdict.

        The proposal splits the platform's verification by domain (Pillar 1/2).
        The four independent oracles run over the CODE domain: a produced code
        artifact is checked by held-out tests, metamorphic relations, a
        cross-family differential, and property fuzzing, and an attack succeeds
        (is undetected) when it gets past that ensemble. A scored model (the
        fraud detector, and later the anomaly detectors) produces a numeric
        artifact the code oracles cannot check; its evasion is measured by the
        target's own ``query_target`` score, exactly as the red search already
        determines (Pillar 2). True means the oracle verdict is the success
        signal; False means the red search's score-based evasion is. Read-only so
        a plain class attribute or a frozen dataclass field both satisfy it.
        """
        ...

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
