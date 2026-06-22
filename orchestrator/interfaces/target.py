"""The Target port. A target adapter maps one kind of AI-system-under-verification
onto this Protocol (docs/VOCABULARY.md "Adapter"). The orchestrator depends on this
Protocol; concrete adapters live in modules/targets/ and are wired in wiring.py."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from shared.types.enums import Shape
from shared.types.results import HealthStatus, ProducerResult


@runtime_checkable
class Target(Protocol):
    """The system under verification (the producer)."""

    kind: str       # "fraud" | "code_agent" | "dummy"
    shape: Shape

    async def submit(self, payload: Mapping[str, Any]) -> ProducerResult:
        """Run the producer on one input and return its output plus audit."""
        ...

    async def health(self) -> HealthStatus:
        """Self-test for the /health route (spec US-8)."""
        ...
