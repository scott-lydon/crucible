"""In-memory Measure sink: pub/sub for Server-Sent Events plus the health-probe
registry. Implements orchestrator.interfaces.MeasureSink. The dashboard reads from
Postgres via this sink's event stream, never from the loop directly (plan.md
section 4)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from typing import Any

from orchestrator.interfaces.measure import HealthProbe
from shared.types.ids import RunId
from shared.types.results import HealthStatus

_MAX_HISTORY = 2000


class InMemoryMeasureSink:
    """One process-local sink. Adequate for the single-operator two-week build
    (spec.md section 4 "Multi-tenant isolation. Out of scope")."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[Mapping[str, Any]]]] = {}
        self._history: dict[str, list[Mapping[str, Any]]] = {}
        self._probes: dict[str, HealthProbe] = {}

    async def emit(self, run_id: RunId, kind: str, payload: Mapping[str, Any]) -> None:
        event: dict[str, Any] = {"run_id": str(run_id), "kind": kind, "payload": dict(payload)}
        hist = self._history.setdefault(str(run_id), [])
        hist.append(event)
        if len(hist) > _MAX_HISTORY:
            del hist[: len(hist) - _MAX_HISTORY]
        for queue in self._subscribers.get(str(run_id), []):
            await queue.put(event)

    async def subscribe(self, run_id: RunId) -> AsyncIterator[Mapping[str, Any]]:
        """Yield this run's past events, then live ones as they arrive."""
        queue: asyncio.Queue[Mapping[str, Any]] = asyncio.Queue()
        self._subscribers.setdefault(str(run_id), []).append(queue)
        try:
            for past in list(self._history.get(str(run_id), [])):
                yield past
            while True:
                yield await queue.get()
        finally:
            self._subscribers.get(str(run_id), []).remove(queue)

    def register_health_probe(self, name: str, probe: HealthProbe) -> None:
        self._probes[name] = probe

    async def run_health(self) -> Mapping[str, HealthStatus]:
        results: dict[str, HealthStatus] = {}
        for name, probe in self._probes.items():
            try:
                results[name] = await probe()
            except Exception as exc:  # noqa: BLE001 — a probe failing is a red leaf, not a crash
                results[name] = HealthStatus(status="red", error=str(exc))
        return results
