"""Money value object.

Wraps Decimal so a count can never be passed where a dollar amount is
expected, and so dollar arithmetic never inherits binary-float rounding
noise. Construct from external input via `Money.of(...)`, which routes
through str() to keep the Decimal exact.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Self

from .errors import DomainValidationError


@dataclass(frozen=True, slots=True)
class Money:
    """A non-negative dollar amount."""

    dollars: Decimal

    def __post_init__(self) -> None:
        if self.dollars < 0:
            raise DomainValidationError(
                f"Money must be non-negative; got {self.dollars}. "
                f"A negative cost is a measurement bug upstream, not a valid value."
            )

    @classmethod
    def zero(cls) -> Self:
        return cls(Decimal("0"))

    @classmethod
    def of(cls, amount: str | int | float | Decimal) -> Self:
        """Build Money from external input, going through str() so a float
        like 0.1 does not smuggle in binary-float noise."""
        return cls(Decimal(str(amount)))

    def __add__(self, other: Money) -> Money:
        return Money(self.dollars + other.dollars)

    def __str__(self) -> str:
        return f"${self.dollars}"
