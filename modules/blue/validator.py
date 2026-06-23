"""Holdout validator — measures detection recovery on held-out evasions.

The holdout is the set of mutated-but-still-fraud samples the OLD detector
cleared (the red loop's successful evasions). The OLD detector cleared them by
construction, so ``detection_before`` is ~0. The validator scores the SAME
samples with the NEW (retrained) detector and reports the fraction now caught.
``recovered = detection_after - detection_before``: the honest gain.

Generic over the victim: ``label_fn`` and ``threshold`` are injected. Only the
samples that are genuinely still positive (``label_fn`` true) are counted — a
mutation that flipped the label is not a real evasion and must not inflate the
numbers.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from orchestrator.interfaces import Detector


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Detection rates on the holdout evasions, before vs after retraining."""

    detection_before: float
    detection_after: float
    recovered: float
    n: int


class HoldoutValidator:
    """Computes the NEW detector's detection rate on the held-out evasions."""

    def validate(
        self,
        new_detector: Detector,
        holdout_samples: Sequence[object],
        label_fn: Callable[[object], bool],
        threshold: float,
        *,
        old_detector: Detector | None = None,
    ) -> ValidationResult:
        """Detection rate of ``new_detector`` on the still-fraud holdout samples.

        Only genuinely-positive samples (``label_fn`` true) are scored. When
        ``old_detector`` is supplied, ``detection_before`` is measured directly
        on it; otherwise it is 0.0 (the holdout is, by construction, what the old
        detector cleared). ``detection_after`` = caught fraction by the new
        detector. ``recovered`` = after - before.
        """
        positives = [s for s in holdout_samples if label_fn(s)]
        n = len(positives)
        if n == 0:
            return ValidationResult(
                detection_before=0.0, detection_after=0.0, recovered=0.0, n=0
            )

        after_caught = sum(1 for s in positives if new_detector.score(s) >= threshold)
        detection_after = after_caught / n

        if old_detector is not None:
            before_caught = sum(
                1 for s in positives if old_detector.score(s) >= threshold
            )
            detection_before = before_caught / n
        else:
            detection_before = 0.0

        return ValidationResult(
            detection_before=detection_before,
            detection_after=detection_after,
            recovered=detection_after - detection_before,
            n=n,
        )
