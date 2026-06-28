"""Held-out validator (PR3 port C1/C2).

The held-out attack set is defined up front and must never overlap the attacks the patch
was trained on. ``assert_disjoint`` refuses a contaminated set with a typed
``HoldoutContamination`` rather than reporting a recovery the patch did not earn;
``detection_rate`` is the fraction of held-out attacks the (new) model now scores at or
above the decision threshold, measured from the real model's predictions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from modules.blue.errors import HoldoutContamination

THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class HoldoutValidator:
    """Contamination guard plus detection measurement on a held-out attack set."""

    threshold: float = THRESHOLD

    def assert_disjoint(self, train_ids: set[str], holdout_ids: set[str]) -> None:
        """Refuse if any held-out attack also trained the patch (US-7)."""
        overlap = train_ids & holdout_ids
        if overlap:
            raise HoldoutContamination(
                f"Holdout contamination: {len(overlap)} attack(s) overlap training "
                f"(ids: {sorted(overlap)[:5]}); a held-out score that shares examples "
                f"with training is leakage, not validation."
            )

    def detection_rate(self, scores: Sequence[float]) -> float:
        """Fraction of held-out attacks scored at or above the decision threshold."""
        if not scores:
            return 0.0
        return sum(1 for s in scores if s >= self.threshold) / len(scores)
