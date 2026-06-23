from shared.types import VerdictContext, OracleVote, OracleKind, Vote


class LlmJudgeMockOracle:
    """Deterministic MOCK judge (no real LLM call). One labeled 0.5 vote."""

    @property
    def kind(self) -> OracleKind:
        return OracleKind.LLM_JUDGE_MOCK

    def vote(self, ctx: VerdictContext) -> OracleVote:
        # Spec/target-agnostic MOCK heuristic (no real LLM, no feature names):
        # a sample cleared by a wide margin "reads as evasion" to the mock judge.
        suspicious = ctx.detector_score < (ctx.threshold * 0.5)
        return OracleVote(
            kind=self.kind, vote=Vote.FAIL if suspicious else Vote.PASS, weight=0.5,
            reason=("mock judge: cleared by a wide margin reads as evasion"
                    if suspicious else "mock judge: nothing obviously wrong"),
            evidence={"mock": True, "note": "one vote; not a real LLM"})
