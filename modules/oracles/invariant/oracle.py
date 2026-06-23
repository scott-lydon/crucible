from shared.types import VerdictContext, OracleVote, OracleKind, Vote
from modules.targets.synth.constants import V_THRESH


class InvariantOracle:
    """Hard domain rule: country_mismatch AND high-velocity must be flagged,
    regardless of amount. Fires FAIL when the detector clears such a txn."""

    @property
    def kind(self) -> OracleKind:
        return OracleKind.INVARIANT

    def vote(self, ctx: VerdictContext) -> OracleVote:
        must_flag = ctx.txn.country_mismatch and ctx.txn.velocity > V_THRESH
        cleared = ctx.detector_score < ctx.threshold
        violated = must_flag and cleared
        return OracleVote(
            kind=self.kind, vote=Vote.FAIL if violated else Vote.PASS, weight=1.0,
            reason=("country_mismatch + high velocity cleared by detector"
                    if violated else "no hard invariant violated"),
            evidence={"must_flag": must_flag, "cleared": cleared})
