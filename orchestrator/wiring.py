"""Dependency injection. This is the ONLY module allowed to import both a concrete
class and the interface it satisfies (constitution.md section 2). Every other module
sees only interfaces.

As pillars land, their concrete classes are registered here. Tests build their own
container (``build_container``) injecting ScriptedLLM-backed fakes."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text

from modules.measure.sink import InMemoryMeasureSink
from orchestrator.interfaces import MeasureSink, Target
from shared.persistence.db import session_scope
from shared.types.results import HealthStatus


@dataclass
class Container:
    sink: MeasureSink
    targets: dict[str, Target] = field(default_factory=dict)

    def register_target(self, target: Target) -> None:
        self.targets[target.kind] = target

    def get_target(self, kind: str) -> Target:
        if kind not in self.targets:
            raise KeyError(
                f"No target adapter registered for kind={kind!r}. "
                f"Registered: {sorted(self.targets)}"
            )
        return self.targets[kind]


async def _db_health() -> HealthStatus:
    try:
        async with session_scope() as session:
            await session.execute(text("SELECT 1"))
        return HealthStatus(status="green", detail={"dependency": "postgres"})
    except Exception as exc:  # noqa: BLE001 — surface DB-down as a red leaf, not a crash
        return HealthStatus(status="red", error=str(exc))


def build_container() -> Container:
    """Construct the wired container. Targets/oracles/red/blue register as their
    slices land; slice 0 wires the sink and the persistence health probe."""
    sink: MeasureSink = InMemoryMeasureSink()
    sink.register_health_probe("shared/persistence", _db_health)
    return Container(sink=sink)


_container: Container | None = None


def get_container() -> Container:
    global _container
    if _container is None:
        _container = build_container()
    return _container


def set_container(container: Container) -> None:
    """Override the process container (tests)."""
    global _container
    _container = container
