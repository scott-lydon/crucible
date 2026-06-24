"""Shared evaluation of a `must_flag_when` invariant's condition grammar.

The `must_flag_when` invariant declares an `all_of` list of conditions, each
`{"feature": <name>, "<op>": <value>}` with op in (eq, gt, lt, ge, le). This is
the single point of truth for evaluating that grammar against an opaque sample,
reused by both the InvariantOracle (checks observed samples) and the
PropertyFuzzOracle (generatively searches for samples that satisfy it). The
harness hardcodes NO feature names — the spec supplies them.
"""

from collections.abc import Mapping, Sequence
from typing import cast

from shared.types.feature import feature

# Comparison operators a `must_flag_when` invariant may use in its conditions.
OPS = ("eq", "gt", "lt", "ge", "le")


def condition_holds(sample: object, cond: Mapping[str, object]) -> bool:
    """Evaluate one {"feature": <name>, "<op>": <value>} condition vs `sample`."""
    name = cast(str, cond["feature"])
    actual = feature(sample, name)
    for op in OPS:
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
    raise ValueError(f"invariant condition has no known operator {tuple(OPS)}: {dict(cond)}")


def all_conditions_hold(sample: object, all_of: Sequence[Mapping[str, object]]) -> bool:
    """True iff every condition in an invariant's `all_of` list holds for `sample`."""
    return all(condition_holds(sample, cond) for cond in all_of)
