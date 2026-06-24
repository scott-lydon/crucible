"""Shared evaluation of a `must_flag_when` invariant's condition grammar.

The `must_flag_when` invariant declares an `all_of` list of conditions, each
`{"feature": <name>, "<op>": <value>}` with op in (eq, gt, lt, ge, le, in_).
`in_` is set membership (value is a list); the others are scalar comparisons.
This is the single point of truth for evaluating that grammar against an opaque
sample, reused by both the InvariantOracle (checks observed samples) and the
PropertyFuzzOracle (generatively searches for samples that satisfy it). The
harness hardcodes NO feature names — the spec supplies them.
"""

from collections.abc import Collection, Mapping, Sequence
from typing import cast

from shared.types.feature import feature

# Comparison operators a `must_flag_when` invariant may use in its conditions.
# `in_` (trailing underscore, since `in` is a Python keyword and reads cleanly
# in YAML) tests set membership against a declared list — the only operator that
# can express a disjoint set like the night-hour window {22,23,0,1,2,3}, which
# wraps midnight and so cannot be expressed as a single gt/lt range.
OPS = ("eq", "gt", "lt", "ge", "le", "in_")


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
        if op == "in_":
            # Set membership: the declared value is a list/collection of allowed
            # values. A scalar (non-collection) operand is a malformed spec.
            if isinstance(expected, str) or not isinstance(expected, Collection):
                raise ValueError(
                    f"invariant condition 'in_' expects a list value, got "
                    f"{type(expected).__name__}: {dict(cond)}"
                )
            return actual in expected
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
