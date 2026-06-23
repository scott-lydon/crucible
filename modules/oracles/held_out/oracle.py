from shared.types import VerdictContext, OracleVote, OracleKind, Vote
from modules.targets.synth.rule import is_fraud


class HeldOutOracle:
    """Independent label authority. Certifies ground truth and grades whether
    the detector missed a true-fraud case. It does not 'catch' — it judges."""

    @property
    def kind(self) -> OracleKind:
        return OracleKind.HELD_OUT

    def vote(self, ctx: VerdictContext) -> OracleVote:
        cleared = ctx.detector_score < ctx.threshold
        truly_fraud = is_fraud(ctx.txn)            # recompute from sealed rule, ignore ctx.true_label
        missed = cleared and truly_fraud
        return OracleVote(
            kind=self.kind,
            vote=Vote.FAIL if missed else Vote.PASS,
            weight=1.0,
            reason=("detector cleared a transaction the ground-truth rule labels fraud"
                    if missed else "detector decision agrees with ground truth"),
            evidence={"cleared": cleared, "ground_truth_fraud": truly_fraud})
