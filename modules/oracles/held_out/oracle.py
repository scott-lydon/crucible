from collections.abc import Callable

from shared.types import VerdictContext, OracleVote, OracleKind, Vote


class HeldOutOracle:
    """Independent label authority. Certifies ground truth and grades whether
    the detector missed a true-positive case. It does not 'catch' — it judges.

    The ground-truth label function is injected so the harness never depends on
    any particular victim's rule.
    """

    def __init__(self, label_fn: Callable[[object], bool]) -> None:
        self._label_fn = label_fn

    @property
    def kind(self) -> OracleKind:
        return OracleKind.HELD_OUT

    def vote(self, ctx: VerdictContext) -> OracleVote:
        cleared = ctx.detector_score < ctx.threshold
        truly_fraud = self._label_fn(ctx.sample)   # recompute from sealed rule, ignore ctx.true_label
        missed = cleared and truly_fraud
        return OracleVote(
            kind=self.kind,
            vote=Vote.FAIL if missed else Vote.PASS,
            weight=1.0,
            reason=("detector cleared a transaction the ground-truth rule labels fraud"
                    if missed else "detector decision agrees with ground truth"),
            evidence={"cleared": cleared, "ground_truth_fraud": truly_fraud})
