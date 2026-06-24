"""TargetOutput value object.

What a target returned for one submission. `output` is the raw artifact (a
fraud probability rendered as a float, or a Python source string for the
code agent). `score` is the target's own numeric signal where it has one
(fraud probability), None where it does not (code agent). `audit` is the
producer-side reasoning trace.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .audit import AuditTrace


@dataclass(frozen=True, slots=True)
class TargetOutput:
    """The artifact, optional score, and producer audit from one submission."""

    output: Any
    score: float | None
    audit: AuditTrace
