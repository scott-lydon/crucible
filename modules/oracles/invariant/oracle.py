from collections.abc import Mapping
from typing import cast

from shared.types import VerdictContext, OracleVote, OracleKind, Vote
from shared.types.invariant_eval import all_conditions_hold


class InvariantOracle:
    """SealedSpec-driven hard-rule engine.

    For each `must_flag_when` invariant in the spec, evaluates its `all_of`
    conditions against the sample. If ALL conditions hold yet the detector
    cleared the sample, that invariant is violated. The harness hardcodes NO
    feature names; the spec supplies them.
    """

    @property
    def kind(self) -> OracleKind:
        return OracleKind.INVARIANT

    def describe(self) -> str:
        return (
            "invariant oracle: for each declared `must_flag_when` invariant, if "
            "ALL of its conditions hold on the sample yet the detector cleared "
            "it, the invariant is VIOLATED and the oracle FAILS the detector. "
            "The conditions come from the sealed spec's declared invariants."
        )

    def vote(self, ctx: VerdictContext) -> OracleVote:
        cleared = ctx.detector_score < ctx.threshold
        violated: list[str] = []
        for inv in ctx.spec.invariants:
            if inv.kind != "must_flag_when":
                continue
            all_of = cast(list[Mapping[str, object]], inv.params.get("all_of", []))
            must_flag = all_conditions_hold(ctx.sample, all_of)
            if must_flag and cleared:
                violated.append(inv.name)
        is_violated = bool(violated)
        return OracleVote(
            kind=self.kind,
            vote=Vote.FAIL if is_violated else Vote.PASS,
            weight=1.0,
            reason=(f"invariant(s) violated (cleared despite must-flag): {', '.join(violated)}"
                    if is_violated else "no hard invariant violated"),
            evidence={"violated": violated, "cleared": cleared})
