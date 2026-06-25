"""Hypothesis strategy that GENERATES rich SparkovTxn samples for property-fuzz.

The strategy draws across realistic ranges for the FULL rich feature menu the
record now carries — static/contextual (amt, cat_risk, merchant_risk, age,
city_pop) and behavioral/temporal/geo (velocity, day_of_week, geo_distance_km).
The property-fuzz oracle searches this space for an input that satisfies a
declared ``must_flag_when`` invariant yet the deployed (behavior-blind) victim
clears — a real counterexample.

This lives with the victim (not the harness) so the oracle hardcodes no feature
names — the victim owns its sample shape and ranges, injected via wiring.
"""

from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy

from examples.targets.fraud_sparkov.record import SparkovTxn


def sparkov_strategy() -> SearchStrategy[SparkovTxn]:
    """Generate rich SparkovTxn across realistic feature ranges."""
    return st.builds(
        SparkovTxn,
        txn_index=st.integers(min_value=0, max_value=10_000),
        amt=st.floats(
            min_value=0.0, max_value=2000.0, allow_nan=False, allow_infinity=False
        ),
        cat_risk=st.integers(min_value=0, max_value=1),
        merchant_risk=st.floats(
            min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
        ),
        age=st.integers(min_value=18, max_value=95),
        city_pop=st.integers(min_value=100, max_value=3_000_000),
        velocity=st.integers(min_value=0, max_value=50),
        hour=st.integers(min_value=0, max_value=23),
        day_of_week=st.integers(min_value=0, max_value=6),
        geo_distance_km=st.floats(
            min_value=0.0, max_value=10_000.0, allow_nan=False, allow_infinity=False
        ),
    )
