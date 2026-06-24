"""AuditTrace value object.

The full reasoning surface for one action, stored as JSONB. A trace that
records only "ok" or "failed" is a bug (coding-practices.md section 3): each
step carries what was observed and why it led to the outcome, so an auditor
can reconstruct the decision without re-running it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditStep:
    """One observable step in an action's reasoning chain."""

    label: str
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AuditTrace:
    """An ordered, non-empty record of how an action reached its outcome."""

    summary: str
    steps: tuple[AuditStep, ...]

    def as_json(self) -> dict[str, Any]:
        """Serialize for the JSONB column and the dashboard Inspect panel."""
        return {
            "summary": self.summary,
            "steps": [{"label": s.label, "detail": s.detail} for s in self.steps],
        }
