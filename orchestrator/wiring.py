"""Dependency injection. This is the ONLY module allowed to import both a concrete
class and the interface it satisfies (constitution.md section 2). Every other module
sees only interfaces.

As pillars land, their concrete classes are registered here. Tests build their own
container (``build_container``) injecting ScriptedLLM-backed fakes."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from sqlalchemy import text

from modules.blue.agent import FraudBlueAgent
from modules.measure.sink import InMemoryMeasureSink
from modules.oracles.aggregator import run_verdict
from modules.oracles.differential.oracle import FraudDifferentialOracle
from modules.oracles.held_out.oracle import FraudHeldOutOracle
from modules.oracles.llm_judge.oracle import LLMJudgeOracle
from modules.oracles.metamorphic.oracle import FraudMetamorphicOracle
from modules.oracles.property_fuzz.oracle import FraudPropertyFuzzOracle
from modules.red.llm_hybrid import LLMHybridFraudRed
from modules.red.static import StaticRedAgent
from modules.targets.dummy.target import DummyTarget
from modules.targets.fraud.target import FraudTarget
from orchestrator.interfaces import (
    BlueAgent,
    HealthProbe,
    MeasureSink,
    Oracle,
    RedAgent,
    Target,
    VerifyFn,
)
from shared.config import load_settings
from shared.llm import ScriptedLLM, make_llm
from shared.llm.client import LLMClient
from shared.persistence.db import session_scope
from shared.telemetry.log import get_logger
from shared.types.results import HealthStatus

_log = get_logger("orchestrator.wiring")


def _untrained_probe(message: str) -> HealthProbe:
    async def probe() -> HealthStatus:
        return HealthStatus(status="amber", error=message)

    return probe


def _judge_llm() -> LLMClient:
    """Real Opus when CRUCIBLE_REAL_JUDGE=1 and a key is present; otherwise a free,
    deterministic ScriptedLLM that votes 'ok' (mock mode, spec US-15)."""
    settings = load_settings()
    if os.environ.get("CRUCIBLE_REAL_JUDGE") == "1" and settings.openrouter_api_key:
        return make_llm(settings.opus_model)
    return ScriptedLLM(
        lambda _system, _prompt: '{"verdict": "ok", "reason": "mock judge: no violation asserted"}',
        model="scripted-judge",
    )


def _red_llm() -> LLMClient:
    """Real Sonnet (the AI attacker reasons about strategy) when CRUCIBLE_REAL_RED=1;
    otherwise a deterministic ScriptedLLM that picks the high-gain features. Either way
    scipy.optimize does the real evasion search."""
    settings = load_settings()
    if os.environ.get("CRUCIBLE_REAL_RED") == "1" and settings.openrouter_api_key:
        return make_llm(settings.sonnet_model)
    return ScriptedLLM(
        lambda _system, _prompt: (
            '{"tactic": "margin-drift", "features": ["V14","V12","V10","V17","V4","V3",'
            '"V7","V11","V16","V18","V9","V21"], "rationale": "perturb the highest-gain '
            'features to drive the model log-odds below zero"}'
        ),
        model="scripted-red",
    )


@dataclass
class Container:
    sink: MeasureSink
    default_red: RedAgent
    verify: VerifyFn
    targets: dict[str, Target] = field(default_factory=dict)
    oracles: dict[str, list[Oracle]] = field(default_factory=dict)
    reds: dict[str, RedAgent] = field(default_factory=dict)
    blues: dict[str, BlueAgent] = field(default_factory=dict)

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

    def register_red(self, target_kind: str, agent: RedAgent) -> None:
        self.reds[target_kind] = agent

    def red_for(self, target_kind: str) -> RedAgent:
        return self.reds.get(target_kind, self.default_red)

    def register_blue(self, target_kind: str, agent: BlueAgent) -> None:
        self.blues[target_kind] = agent

    def blue_for(self, target_kind: str) -> BlueAgent | None:
        return self.blues.get(target_kind)


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

    container = Container(sink=sink, default_red=static_red, verify=run_verdict)
    container.register_target(dummy)

    # Fraud target loads from the trained artifact; if it has not been trained yet the
    # /health leaf reports amber rather than the platform failing to start.
    fraud: FraudTarget | None = None
    try:
        fraud = FraudTarget.load()
        container.register_target(fraud)
        sink.register_health_probe("targets/fraud", fraud.health)
    except FileNotFoundError as exc:
        _log.warning("fraud_model_missing", error=str(exc))
        sink.register_health_probe("targets/fraud", _untrained_probe(str(exc)))

    # Fraud red agent: the AI attacker — an LLM reasons about which features to attack,
    # scipy.optimize crafts the adversarial evasion of a real fraud (true label kept in
    # metadata for the held-out oracle). Mock LLM by default, real Sonnet on the flag.
    if fraud is not None:
        fraud_red = LLMHybridFraudRed(
            _red_llm(), fraud.predict_sync, fraud.raw_margin,
            fraud.feature_names, fraud.feature_importances,
        )
        container.register_red("fraud", fraud_red)
        sink.register_health_probe("red/fraud/llm-hybrid", fraud_red.health)

    # Fraud oracle ensemble (judge appends in slice 9).
    held_out = FraudHeldOutOracle()
    container.register_oracle("fraud", held_out)
    sink.register_health_probe("oracles/fraud/held_out", held_out.health)
    try:
        differential = FraudDifferentialOracle.load()
        container.register_oracle("fraud", differential)
        sink.register_health_probe("oracles/fraud/differential", differential.health)
    except FileNotFoundError as exc:
        _log.warning("fraud_iso_missing", error=str(exc))
        sink.register_health_probe("oracles/fraud/differential", _untrained_probe(str(exc)))
    if fraud is not None:
        metamorphic = FraudMetamorphicOracle(fraud.predict_sync, fraud.feature_names)
        container.register_oracle("fraud", metamorphic)
        sink.register_health_probe("oracles/fraud/metamorphic", metamorphic.health)
        fuzz = FraudPropertyFuzzOracle(fraud.predict_sync, fraud.feature_names)
        container.register_oracle("fraud", fuzz)
        sink.register_health_probe("oracles/fraud/property_fuzz", fuzz.health)

    # LLM judge (half vote) — target-agnostic; mock by default, real Opus on demand.
    judge = LLMJudgeOracle(_judge_llm())
    container.register_oracle("fraud", judge)
    sink.register_health_probe("oracles/fraud/llm_judge", judge.health)

    # Blue hardening loop for fraud (retrain on adversarial samples, held-out validate).
    fraud_blue = FraudBlueAgent(base_version=1)
    container.register_blue("fraud", fraud_blue)
    sink.register_health_probe("blue/fraud", fraud_blue.health)

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
