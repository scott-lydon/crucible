from shared.types import VerdictContext, OracleVote, OracleKind, Vote


class DifferentialStubOracle:
    """v0 STUB. Renders a card but abstains (weight 0). Later: IsolationForest
    second opinion from a different model family."""

    @property
    def kind(self) -> OracleKind:
        return OracleKind.DIFFERENTIAL_STUB

    def vote(self, ctx: VerdictContext) -> OracleVote:
        return OracleVote(
            kind=self.kind, vote=Vote.ABSTAIN, weight=0.0,
            reason="stub — differential oracle not evaluated in v0",
            evidence={"stub": True})
