"""Dependency injection. This is the ONLY module allowed to import both a concrete
class and the interface it satisfies (constitution.md section 2). Every other module
sees only interfaces.

As pillars land, their concrete classes are registered here. Tests build their own
container (``build_container``) injecting ScriptedLLM-backed fakes."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text

from modules.measure.sink import InMemoryMeasureSink
from modules.oracles.differential.oracle import FraudDifferentialOracle
from modules.red.static import StaticRedAgent
from modules.targets.dummy.target import DummyTarget
from modules.targets.fraud.target import FraudTarget
from orchestrator.interfaces import HealthProbe, MeasureSink, Oracle, RedAgent, Target
from shared.persistence.db import session_scope
from shared.telemetry.log import get_logger
from shared.types.results import HealthStatus

_log = get_logger("orchestrator.wiring")


def _untrained_probe(message: str) -> HealthProbe:
    async def probe() -> HealthStatus:
        return HealthStatus(status="amber", error=message)

    return probe


@dataclass
class Container:
    sink: MeasureSink
    red: RedAgent
    targets: dict[str, Target] = field(default_factory=dict)
    oracles: dict[str, list[Oracle]] = field(default_factory=dict)

    def register_target(self, target: Target) -> None:
        self.targets[target.kind] = target

    def get_target(self, kind: str) -> Target:
        if kind not in self.targets:
            raise KeyError(
                f"No target adapter registered for kind={kind!r}. "
                f"Registered: {sorted(self.targets)}"
            )
        return self.targets[kind]

    def register_oracle(self, target_kind: str, oracle: Oracle) -> None:
        self.oracles.setdefault(target_kind, []).append(oracle)

    def oracles_for(self, target_kind: str) -> list[Oracle]:
        return self.oracles.get(target_kind, [])


async def _db_health() -> HealthStatus:
    try:
        async with session_scope() as session:
            await session.execute(text("SELECT 1"))
        return HealthStatus(status="green", detail={"dependency": "postgres"})
    except Exception as exc:  # noqa: BLE001 — surface DB-down as a red leaf, not a crash
        return HealthStatus(status="red", error=str(exc))


def build_container() -> Container:
    """Construct the wired container. Oracles/blue register as their slices land;
    slice 1 wires the dummy target and the static red agent so the loop runs a real
    round end to end."""
    sink: MeasureSink = InMemoryMeasureSink()
    sink.register_health_probe("shared/persistence", _db_health)

    dummy = DummyTarget()
    static_red = StaticRedAgent()
    sink.register_health_probe("targets/dummy", dummy.health)
    sink.register_health_probe("red/static", static_red.health)

    container = Container(sink=sink, red=static_red)
    container.register_target(dummy)

    # Fraud target loads from the trained artifact; if it has not been trained yet the
    # /health leaf reports amber rather than the platform failing to start.
    try:
        fraud = FraudTarget.load()
        container.register_target(fraud)
        sink.register_health_probe("targets/fraud", fraud.health)
    except FileNotFoundError as exc:
        _log.warning("fraud_model_missing", error=str(exc))
        sink.register_health_probe("targets/fraud", _untrained_probe(str(exc)))

    # Fraud oracles. Differential (IsolationForest) lands in slice 7; the held-out,
    # metamorphic, property-fuzz and judge oracles append here in slices 5/6/8/9.
    try:
        differential = FraudDifferentialOracle.load()
        container.register_oracle("fraud", differential)
        sink.register_health_probe("oracles/fraud/differential", differential.health)
    except FileNotFoundError as exc:
        _log.warning("fraud_iso_missing", error=str(exc))
        sink.register_health_probe("oracles/fraud/differential", _untrained_probe(str(exc)))

    return container


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
