"""Measure port.

Where the loop sends every persisted event for the dashboard, and where each
subcomponent registers its self-test so the /health route can walk them
(ARCHITECTURE.md section 7).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from shared.types import ProbeResult, RunId


@runtime_checkable
class MeasureSink(Protocol):
    """The dashboard-facing sink and health registry."""

    async def emit(self, run_id: RunId, event_type: str, payload: dict[str, Any]) -> None:
        """Persist one event and push it to any live SSE subscriber."""
        ...

    def register_health_probe(
        self,
        name: str,
        probe_fn: Callable[[], Awaitable[ProbeResult]],
    ) -> None:
        """Register a subcomponent self-test the /health route can invoke."""
        ...
