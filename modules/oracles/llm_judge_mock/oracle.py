from shared.types import VerdictContext, OracleVote, OracleKind, Vote


class LlmJudgeMockOracle:
    """Deterministic MOCK judge (no real LLM call). One labeled 0.5 vote."""

    @property
    def kind(self) -> OracleKind:
        return OracleKind.LLM_JUDGE_MOCK

    def vote(self, ctx: VerdictContext) -> OracleVote:
        # crude heuristic: low amount + high velocity looks suspicious to the "judge"
        suspicious = ctx.txn.amount < 100.0 and ctx.txn.velocity > 5
        return OracleVote(
            kind=self.kind, vote=Vote.FAIL if suspicious else Vote.PASS, weight=0.5,
            reason=("mock judge: low amount with high velocity reads as evasion"
                    if suspicious else "mock judge: nothing obviously wrong"),
            evidence={"mock": True, "note": "one vote; not a real LLM"})
