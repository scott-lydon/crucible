from collections.abc import Mapping
from typing import cast

from shared.types import VerdictContext, OracleVote, OracleKind, Vote, feature

# Comparison operators a `must_flag_when` invariant may use in its conditions.
_OPS = ("eq", "gt", "lt", "ge", "le")


def _condition_holds(sample: object, cond: Mapping[str, object]) -> bool:
    """Evaluate one {"feature": <name>, "<op>": <value>} condition vs `sample`."""
    name = cast(str, cond["feature"])
    actual = feature(sample, name)
    for op in _OPS:
        if op not in cond:
            continue
        expected = cond[op]
        if op == "eq":
            return actual == expected
        # Ordered comparisons require comparable (numeric) operands.
        a = cast(float, actual)
        e = cast(float, expected)
        if op == "gt":
            return a > e
        if op == "lt":
            return a < e
        if op == "ge":
            return a >= e
        if op == "le":
            return a <= e
    raise ValueError(f"invariant condition has no known operator {tuple(_OPS)}: {dict(cond)}")


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

    def vote(self, ctx: VerdictContext) -> OracleVote:
        cleared = ctx.detector_score < ctx.threshold
        violated: list[str] = []
        for inv in ctx.spec.invariants:
            if inv.kind != "must_flag_when":
                continue
            all_of = cast(list[Mapping[str, object]], inv.params.get("all_of", []))
            must_flag = all(_condition_holds(ctx.sample, cond) for cond in all_of)
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
