import dataclasses
from collections.abc import Callable
from typing import Any, cast

from shared.types import SealedSpec, feature


class MetamorphicEvasionAdversary:
    """SealedSpec-driven evasion adversary.

    Picks the first metamorphic relation that decreases a feature without
    changing the true label, then walks a descending ladder of that feature
    toward the detector's blind spot while preserving the true (target-positive)
    label. Returns None if no evading-yet-still-positive variant exists. The
    harness hardcodes NO feature names; the spec supplies them.
    """

    LADDER = (0.5, 0.25, 0.1, 0.05, 0.02)

    def __init__(self, score_fn: Callable[[object], float],
                 label_fn: Callable[[object], bool], threshold: float,
                 spec: SealedSpec) -> None:
        self._score = score_fn
        self._is_positive = label_fn
        self._threshold = threshold
        self._spec = spec
        self._feat = self._pick_feature(spec)

    @staticmethod
    def _pick_feature(spec: SealedSpec) -> str | None:
        for rel in spec.metamorphic_relations:
            if rel.direction == "decrease" and not rel.label_must_change:
                return rel.feature
        return None

    def mutate(self, sample: object, score: float) -> object | None:
        if self._feat is None:
            return None
        orig = cast(float, feature(sample, self._feat))
        for factor in self.LADDER:
            candidate: object = dataclasses.replace(
                cast(Any, sample), **{self._feat: round(orig * factor, 2)})
            if not self._is_positive(candidate):
                continue                       # would flip the label -> reject
            if self._score(candidate) < self._threshold:
                return candidate               # evades AND still target-positive
        return None
