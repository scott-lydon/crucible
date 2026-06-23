from shared.types import VerdictContext, OracleVote, OracleKind, Vote
from modules.targets.synth.rule import is_fraud


class MetamorphicOracle:
    """Checks metamorphic relations derived from spec invariants."""

    SCORE_DROP = 0.25

    @property
    def kind(self) -> OracleKind:
        return OracleKind.METAMORPHIC

    def vote(self, ctx: VerdictContext) -> OracleVote:
        violations: list[str] = []
        # R1: lowering amount must not change the true label
        if ctx.original_txn is not None:
            label_changed = is_fraud(ctx.original_txn) != is_fraud(ctx.txn)
            big_drop = (ctx.original_score or 0.0) - ctx.detector_score >= self.SCORE_DROP
            if big_drop and not label_changed and is_fraud(ctx.txn):
                violations.append("R1: amount-lowering dropped score but label unchanged")
        # R2: a still-fraud transaction must not be cleared
        if is_fraud(ctx.txn) and ctx.detector_score < ctx.threshold:
            violations.append("R2: true-fraud transaction cleared")
        # R3: non-fraud must not be over-flagged (sanity; passes in this demo)
        if (not is_fraud(ctx.txn)) and ctx.detector_score >= ctx.threshold:
            violations.append("R3: non-fraud over-flagged")
        failed = any(v.startswith(("R1", "R2")) for v in violations)
        return OracleVote(
            kind=self.kind, vote=Vote.FAIL if failed else Vote.PASS, weight=1.0,
            reason="; ".join(violations) or "all metamorphic relations hold",
            evidence={"violations": violations})
