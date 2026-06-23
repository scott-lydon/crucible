from shared.types import VerdictContext, OracleVote, OracleKind, Vote


class InvariantOracle:
    """Hard domain rule: country_mismatch AND high-velocity must be flagged,
    regardless of amount. Fires FAIL when the detector clears such a txn.

    The velocity threshold is injected so the harness never depends on any
    particular victim's constants.
    """

    def __init__(self, velocity_threshold: int) -> None:
        self._velocity_threshold = velocity_threshold

    @property
    def kind(self) -> OracleKind:
        return OracleKind.INVARIANT

    def vote(self, ctx: VerdictContext) -> OracleVote:
        must_flag = ctx.txn.country_mismatch and ctx.txn.velocity > self._velocity_threshold
        cleared = ctx.detector_score < ctx.threshold
        violated = must_flag and cleared
        return OracleVote(
            kind=self.kind, vote=Vote.FAIL if violated else Vote.PASS, weight=1.0,
            reason=("country_mismatch + high velocity cleared by detector"
                    if violated else "no hard invariant violated"),
            evidence={"must_flag": must_flag, "cleared": cleared})
