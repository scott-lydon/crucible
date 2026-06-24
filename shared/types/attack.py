"""Attack value object.

One red-agent attempt against the target. `succeeded` means the attempt got
past the oracle ensemble (an undetected hack); `white_box` and `hybrid` mark
which red mode produced it, so the dashboard can separate black-box from
white-box catch rates (US-14).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .audit import AuditTrace
from .ids import AttackId, RunId
from .money import Money


@dataclass(frozen=True, slots=True)
class Attack:
    """A single attempt to evade or reward-hack the target."""

    attack_id: AttackId
    run_id: RunId
    tactic: str
    payload: dict[str, Any]
    succeeded: bool
    white_box: bool
    hybrid: bool
    dollars_spent: Money
    audit: AuditTrace
