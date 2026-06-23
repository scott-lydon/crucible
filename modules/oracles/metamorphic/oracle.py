from collections.abc import Callable
from typing import cast

from shared.types import VerdictContext, OracleVote, OracleKind, Vote, feature


class MetamorphicOracle:
    """SealedSpec-driven metamorphic relation engine.

    R1 is derived from the spec's metamorphic relations: for a relation whose
    label must NOT change, if the original->current mutation followed that
    relation's feature/direction, the detector score dropped materially, the
    true label is unchanged, and the sample is still target-positive, the
    relation is violated. R2 keeps the simpler check that a still-positive
    sample must not be cleared.

    The ground-truth label function is injected so the harness never depends on
    any particular victim's rule. The harness hardcodes NO feature names.
    """

    SCORE_DROP = 0.25

    def __init__(self, label_fn: Callable[[object], bool]) -> None:
        self._label_fn = label_fn

    @property
    def kind(self) -> OracleKind:
        return OracleKind.METAMORPHIC

    def _followed_relation(self, original: object, current: object,
                           feat: str, direction: str) -> bool:
        """Did the original->current mutation move `feat` in `direction`?"""
        try:
            before = cast(float, feature(original, feat))
            after = cast(float, feature(current, feat))
        except AttributeError:
            return False
        if direction == "decrease":
            return after < before
        if direction == "increase":
            return after > before
        return False

    def vote(self, ctx: VerdictContext) -> OracleVote:
        violations: list[str] = []
        # R1: spec relations where the label must NOT change under the mutation.
        if ctx.original_sample is not None:
            for rel in ctx.spec.metamorphic_relations:
                if rel.label_must_change:
                    continue
                followed = self._followed_relation(
                    ctx.original_sample, ctx.sample, rel.feature, rel.direction)
                if not followed:
                    continue
                big_drop = (ctx.original_score or 0.0) - ctx.detector_score >= self.SCORE_DROP
                label_unchanged = self._label_fn(ctx.original_sample) == self._label_fn(ctx.sample)
                if big_drop and label_unchanged and self._label_fn(ctx.sample):
                    violations.append(
                        f"R1[{rel.name}]: {rel.feature}-{rel.direction} dropped score "
                        "but true label unchanged and still target-positive")
        # R2: a still-positive sample must not be cleared.
        if self._label_fn(ctx.sample) and ctx.detector_score < ctx.threshold:
            violations.append("R2: true-positive sample cleared")
        failed = bool(violations)
        return OracleVote(
            kind=self.kind, vote=Vote.FAIL if failed else Vote.PASS, weight=1.0,
            reason="; ".join(violations) or "all metamorphic relations hold",
            evidence={"violations": violations})
