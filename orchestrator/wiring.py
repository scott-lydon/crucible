"""Dependency injection: which concrete module class satisfies which interface.

This is the only file allowed to import both a concrete module class and the
interface it satisfies (coding-practices.md section 2). Every other file
depends on the interface, never the concrete class.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.oracles.held_out import HeldOutOracle
from modules.oracles.metamorphic import MetamorphicOracle
from modules.targets.code_agent import CodeAgentTarget
from modules.targets.dummy import DummyTarget
from modules.targets.fraud import FraudTarget
from orchestrator.errors import NoOracleRegisteredError, NoTargetRegisteredError
from orchestrator.interfaces import Oracle, Target
from shared.llm import get_llm_client
from shared.sandbox import DockerSandbox
from shared.types import TargetType


@dataclass(frozen=True, slots=True)
class Registry:
    """The wired set of targets and oracles (red and blue added in later slices)."""

    targets: dict[TargetType, Target]
    oracles: tuple[Oracle, ...]

    def target_for(self, target_type: TargetType) -> Target:
        """Return the target adapter for a type, or raise a typed, named error."""
        target = self.targets.get(target_type)
        if target is None:
            known = ", ".join(sorted(t.value for t in self.targets)) or "none"
            raise NoTargetRegisteredError(
                f"No target registered for {target_type.value!r}. "
                f"Registered target types: {known}. Register the adapter in "
                f"orchestrator/wiring.py or correct the run's target_type."
            )
        return target

    def oracle_for(self, name: str) -> Oracle:
        """Return the oracle wired under a name, or raise a typed, named error."""
        for oracle in self.oracles:
            if oracle.name == name:
                return oracle
        known = ", ".join(sorted(o.name for o in self.oracles)) or "none"
        raise NoOracleRegisteredError(
            f"No oracle registered under {name!r}. Registered oracles: {known}. "
            f"Register it in orchestrator/wiring.py or correct the name."
        )


def build_registry() -> Registry:
    """Build a fresh registry.

    Wires the DummyTarget (slice 1) and the CodeAgentTarget (slice 3) on the
    configured LLM client. The fraud target and the other pillars are added to
    this function as their slices land.
    """
    llm = get_llm_client()
    return Registry(
        targets={
            TargetType.DUMMY: DummyTarget(),
            TargetType.CODE_AGENT: CodeAgentTarget(llm=llm),
            TargetType.FRAUD: FraudTarget(),
        },
        oracles=(
            HeldOutOracle(llm=llm, sandbox=DockerSandbox()),
            MetamorphicOracle(llm=llm, sandbox=DockerSandbox()),
        ),
    )


_registry: Registry | None = None


def get_registry() -> Registry:
    """Return the process-wide registry, building it once on first use.

    Module-level singleton (the sanctioned mutable-state exception here): the
    registry is read-only after construction and shared across requests.
    """
    global _registry
    if _registry is None:
        _registry = build_registry()
    return _registry
