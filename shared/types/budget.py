"""AttackBudget value object.

Bounds a run's red-search effort. Either bound reached ends the loop, so a
run can never spin without limit. The budget is set at POST /runs and stays
constant for the run.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import DomainValidationError
from .money import Money


@dataclass(frozen=True, slots=True)
class AttackBudget:
    """Caps red-search attempts and dollar spend for one run."""

    max_attempts: int
    max_dollars: Money

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise DomainValidationError(
                f"AttackBudget.max_attempts must be positive; got {self.max_attempts}. "
                f"A non-positive attempt budget would end the loop before it began."
            )
        # max_dollars is already validated non-negative by Money's constructor.
