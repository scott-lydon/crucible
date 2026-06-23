from collections.abc import Callable

from shared.types import VerdictContext, OracleVote, OracleKind, Vote


class DifferentialOracle:
    """Cross-family differential oracle.

    Compares the TARGET detector's decision against an independent second
    opinion produced by a model from a DIFFERENT family (constitution §1 /
    plan §3: "second implementation from a different model family, require
    agreement"). The harness stays target-agnostic: the second opinion is
    injected as a callable that returns whether the sample is fraud
    (``True``), not fraud (``False``), or "no opinion" (``None``).

    When no second-family model is available the oracle ABSTAINS with weight 0.
    That is honest, not a stub: some victims simply ship no second model.

    When a second opinion exists, the oracle FAILS the detector iff the
    detector CLEARED the sample (score < threshold) yet the independent
    cross-family model FLAGS it as fraud — a real disagreement that overturns
    the detector's "clean" call. Otherwise it PASSES (the two families agree,
    or the cross-family model also clears it).
    """

    def __init__(
        self,
        second_opinion_is_fraud: Callable[[object], bool | None] | None = None,
    ) -> None:
        self._second_opinion_is_fraud = second_opinion_is_fraud

    @property
    def kind(self) -> OracleKind:
        return OracleKind.DIFFERENTIAL

    def vote(self, ctx: VerdictContext) -> OracleVote:
        if self._second_opinion_is_fraud is None:
            return self._abstain()

        flagged = self._second_opinion_is_fraud(ctx.sample)
        if flagged is None:
            return self._abstain()

        cleared = ctx.detector_score < ctx.threshold
        if cleared and flagged:
            return OracleVote(
                kind=self.kind, vote=Vote.FAIL, weight=1.0,
                reason="cross-family model disagrees: flags fraud the target cleared",
                evidence={"cleared": cleared, "second_family_fraud": True})
        return OracleVote(
            kind=self.kind, vote=Vote.PASS, weight=1.0,
            reason="cross-family model agrees with the target's decision",
            evidence={"cleared": cleared, "second_family_fraud": bool(flagged)})

    def _abstain(self) -> OracleVote:
        return OracleVote(
            kind=self.kind, vote=Vote.ABSTAIN, weight=0.0,
            reason="no independent second-family opinion available",
            evidence={"abstained": True})
