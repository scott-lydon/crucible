from collections.abc import Callable

from shared.types import VerdictContext, OracleVote, OracleKind, Vote, Transaction


class MetamorphicOracle:
    """Checks metamorphic relations derived from spec invariants.

    The ground-truth label function is injected so the harness never depends on
    any particular victim's rule.
    """

    SCORE_DROP = 0.25

    def __init__(self, label_fn: Callable[[Transaction], bool]) -> None:
        self._label_fn = label_fn

    @property
    def kind(self) -> OracleKind:
        return OracleKind.METAMORPHIC

    def vote(self, ctx: VerdictContext) -> OracleVote:
        violations: list[str] = []
        # R1: lowering amount must not change the true label
        if ctx.original_txn is not None:
            label_changed = self._label_fn(ctx.original_txn) != self._label_fn(ctx.txn)
            big_drop = (ctx.original_score or 0.0) - ctx.detector_score >= self.SCORE_DROP
            if big_drop and not label_changed and self._label_fn(ctx.txn):
                violations.append("R1: amount-lowering dropped score but label unchanged")
        # R2: a still-fraud transaction must not be cleared
        if self._label_fn(ctx.txn) and ctx.detector_score < ctx.threshold:
            violations.append("R2: true-fraud transaction cleared")
        # R3: non-fraud must not be over-flagged (sanity; passes in this demo)
        if (not self._label_fn(ctx.txn)) and ctx.detector_score >= ctx.threshold:
            violations.append("R3: non-fraud over-flagged")
        failed = any(v.startswith(("R1", "R2")) for v in violations)
        return OracleVote(
            kind=self.kind, vote=Vote.FAIL if failed else Vote.PASS, weight=1.0,
            reason="; ".join(violations) or "all metamorphic relations hold",
            evidence={"violations": violations})
