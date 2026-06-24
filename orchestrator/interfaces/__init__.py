"""The five ports the orchestrator depends on. Concrete implementations live in
modules/ and are bound in orchestrator/wiring.py — the only file allowed to import
both a concrete module class and the interface it satisfies (constitution.md
section 2)."""

from __future__ import annotations

from orchestrator.interfaces.blue import BlueAgent, ConfigurableBlue
from orchestrator.interfaces.measure import HealthProbe, MeasureSink
from orchestrator.interfaces.oracle import Oracle, VerifyFn
from orchestrator.interfaces.red import Primable, RedAgent, SchemeAware, TacticLoader
from orchestrator.interfaces.target import Target

__all__ = [
    "BlueAgent",
    "ConfigurableBlue",
    "HealthProbe",
    "MeasureSink",
    "Oracle",
    "Primable",
    "RedAgent",
    "SchemeAware",
    "TacticLoader",
    "Target",
    "VerifyFn",
]
