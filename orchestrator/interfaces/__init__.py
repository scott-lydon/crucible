"""Pillar interface Protocols, owned by the orchestrator.

Modules implement these; modules never import each other. Defined as
typing.Protocol, never abstract base classes (coding-practices.md section 2).
"""

from __future__ import annotations

from .blue import BlueAgent
from .measure import MeasureSink
from .oracle import Oracle
from .red import RedAgent
from .target import Target

__all__ = ["BlueAgent", "MeasureSink", "Oracle", "RedAgent", "Target"]
