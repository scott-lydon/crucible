"""The Measure port. Every persisted row insert is emitted to this sink, which
fans it out to the dashboard over Server-Sent Events (plan.md section 3 Pillar 4).
The sink also holds the health-probe registry the /health route walks (spec US-8)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from shared.types.ids import RunId
from shared.types.results import HealthStatus

HealthProbe = Callable[[], Awaitable[HealthStatus]]


@runtime_checkable
class MeasureSink(Protocol):
    async def emit(self, run_id: RunId, kind: str, payload: Mapping[str, Any]) -> None:
        """Publish one event (a verdict, attack, patch, run-state change) downstream."""
        ...

    def subscribe(self, run_id: RunId) -> AsyncIterator[Mapping[str, Any]]:
        """Async-iterate this run's events: past events first, then live ones."""
        ...

    def register_health_probe(self, name: str, probe: HealthProbe) -> None:
        """Register a subcomponent self-test, walked by the /health route."""
        ...

    async def run_health(self) -> Mapping[str, HealthStatus]:
        """Run every registered probe and return the aggregate."""
        ...
