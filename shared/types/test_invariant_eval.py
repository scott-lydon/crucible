"""Unit tests for the `must_flag_when` condition grammar, incl. the `in_` op."""

from types import SimpleNamespace

import pytest

from shared.types.invariant_eval import all_conditions_hold, condition_holds


def _s(**kw: object) -> SimpleNamespace:
    return SimpleNamespace(**kw)


def test_scalar_ops() -> None:
    assert condition_holds(_s(amt=300.0), {"feature": "amt", "gt": 250})
    assert not condition_holds(_s(amt=100.0), {"feature": "amt", "gt": 250})
    assert condition_holds(_s(cat_risk=1), {"feature": "cat_risk", "eq": 1})
    assert condition_holds(_s(amt=5.0), {"feature": "amt", "le": 5})
    assert condition_holds(_s(amt=5.0), {"feature": "amt", "ge": 5})
    assert condition_holds(_s(amt=4.0), {"feature": "amt", "lt": 5})


def test_in_set_membership() -> None:
    cond = {"feature": "hour", "in_": [22, 23, 0, 1, 2, 3]}
    # The night window wraps midnight — membership, not a single range.
    for hour in (22, 23, 0, 1, 2, 3):
        assert condition_holds(_s(hour=hour), cond)
    for hour in (4, 12, 21):
        assert not condition_holds(_s(hour=hour), cond)


def test_in_rejects_scalar_value() -> None:
    with pytest.raises(ValueError, match="'in_' expects a list"):
        condition_holds(_s(hour=1), {"feature": "hour", "in_": 1})
    # A bare string is not a valid membership set either.
    with pytest.raises(ValueError, match="'in_' expects a list"):
        condition_holds(_s(hour=1), {"feature": "hour", "in_": "123"})


def test_unknown_operator_raises() -> None:
    with pytest.raises(ValueError, match="no known operator"):
        condition_holds(_s(amt=1.0), {"feature": "amt", "approx": 1})


def test_all_conditions_hold_is_conjunction() -> None:
    sample = _s(cat_risk=1, amt=300.0, hour=23)
    assert all_conditions_hold(
        sample,
        [
            {"feature": "cat_risk", "eq": 1},
            {"feature": "amt", "gt": 250},
            {"feature": "hour", "in_": [22, 23, 0]},
        ],
    )
    assert not all_conditions_hold(
        sample, [{"feature": "cat_risk", "eq": 1}, {"feature": "amt", "gt": 9999}]
    )
