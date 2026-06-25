import dataclasses
import itertools
from collections.abc import Callable, Sequence
from typing import Any, cast

from shared.types import SealedSpec, feature


class MetamorphicEvasionAdversary:
    """Free, multi-feature evasion adversary (no single hard-declared axis).

    The victim keys on a SET of features; this adversary is free to lower ANY of
    them and to COMBINE several at once, searching for a variant the detector
    CLEARS while the true (target-positive) label is preserved. It declares no
    single axis: ``movable_features`` is the whole victim-visible feature set
    (the composition root passes the detector's feature names), and the search
    walks single features first, then pairs, descending a ladder on each.

    Verification is the same as the LLM red's: a candidate "lands" iff the
    detector score drops below threshold AND the label oracle still calls it
    positive. Returns ``None`` if no evading-yet-still-positive variant exists.
    The harness hardcodes NO feature names; ``movable_features`` is supplied.

    Backward compatible: if ``movable_features`` is omitted it falls back to the
    spec's label-preserving decrease relations (so callers that only know the
    spec still get a working, now multi-relation, mutator).
    """

    LADDER = (0.5, 0.25, 0.1, 0.05, 0.02)
    # Cap combination breadth so the deterministic fallback stays cheap/bounded.
    MAX_COMBO = 2

    def __init__(self, score_fn: Callable[[object], float],
                 label_fn: Callable[[object], bool], threshold: float,
                 spec: SealedSpec,
                 movable_features: Sequence[str] | None = None) -> None:
        self._score = score_fn
        self._is_positive = label_fn
        self._threshold = threshold
        self._spec = spec
        self._feats = tuple(movable_features) if movable_features is not None \
            else self._spec_features(spec)

    @staticmethod
    def _spec_features(spec: SealedSpec) -> tuple[str, ...]:
        """The spec's label-preserving decrease relations (fallback only).

        No longer a single axis: every relation that decreases a feature without
        flipping the label is a movable feature.
        """
        return tuple(
            rel.feature
            for rel in spec.metamorphic_relations
            if rel.direction == "decrease" and not rel.label_must_change
        )

    def mutate(self, sample: object, score: float) -> object | None:
        if not self._feats:
            return None
        # Single-feature moves first (cheapest, most interpretable), then
        # multi-feature combinations up to MAX_COMBO. The first landing wins.
        for size in range(1, self.MAX_COMBO + 1):
            for combo in itertools.combinations(self._feats, size):
                candidate = self._try_combo(sample, combo)
                if candidate is not None:
                    return candidate
        return None

    def _try_combo(self, sample: object, feats: tuple[str, ...]) -> object | None:
        """Walk a shared descending ladder over ``feats`` simultaneously."""
        try:
            origins = {f: cast(float, feature(sample, f)) for f in feats}
        except AttributeError:
            return None
        for factor in self.LADDER:
            changes = {f: round(origins[f] * factor, 2) for f in feats}
            candidate: object = dataclasses.replace(cast(Any, sample), **changes)
            if not self._is_positive(candidate):
                continue                       # would flip the label -> reject
            if self._score(candidate) < self._threshold:
                return candidate               # evades AND still target-positive
        return None
