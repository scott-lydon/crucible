"""Held-out validator: re-evaluate detection on an up-front attack set (US-7).

The held-out attack set is defined before the patch is built and must never
overlap the attacks the patch was trained on; the validator refuses a
contaminated set with a typed `HoldoutContamination` rather than reporting a
recovery the patch did not earn. Detection rate is the fraction of held-out
attacks the (new) model now scores at or above the decision threshold, so it is
measured from the real target, never sampled.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from modules.blue.errors import HoldoutContamination
from shared.types import Attack

# An async function that returns the target's score for one payload.
ScoreFn = Callable[[dict[str, Any]], Awaitable[float]]


@dataclass(frozen=True, slots=True)
class HoldoutValidator:
    """Contamination guard plus detection measurement on a held-out attack set."""

    threshold: float = 0.5

    def assert_disjoint(self, train_ids: set[str], holdout_attacks: list[Attack]) -> None:
        """Refuse if any held-out attack also trained the patch (US-7)."""
        holdout_ids = {a.attack_id.value for a in holdout_attacks}
        overlap = train_ids & holdout_ids
        if overlap:
            raise HoldoutContamination(
                f"{len(overlap)} held-out attack(s) also trained the patch "
                f"(ids: {sorted(overlap)[:5]}...); a held-out score that shares "
                f"examples with training is leakage, not validation."
            )

    async def detection_rate(
        self, score_fn: ScoreFn, holdout_attacks: list[Attack]
    ) -> float:
        """Fraction of held-out attacks scored at or above the decision threshold."""
        if not holdout_attacks:
            return 0.0
        detected = 0
        for attack in holdout_attacks:
            score = await score_fn(attack.payload)
            if score >= self.threshold:
                detected += 1
        return detected / len(holdout_attacks)
