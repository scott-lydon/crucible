"""Red-agent port.

The adversarial search engine. It reasons about why an attempt was caught,
proposes a minimal intent-preserving change, queries the target, and
iterates toward an evasion within the budget (ARCHITECTURE.md section 3,
Pillar 2). White-box mode is the same search with the verification scheme
injected into the prompt (US-14).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from shared.types import Attack, AttackBudget, SealedSpec

from .target import Target


@runtime_checkable
class RedAgent(Protocol):
    """The adversarial search engine over a single target."""

    async def search(
        self,
        spec: SealedSpec,
        target: Target,
        budget: AttackBudget,
        *,
        white_box: bool,
    ) -> list[Attack]:
        """Search for evasions until the budget is spent.

        Returns every attempt made, each marked succeeded or not, so the
        dashboard can compute attack-success-rate over the whole search, not
        just the wins.
        """
        ...
