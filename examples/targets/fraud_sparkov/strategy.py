"""Hypothesis strategy that GENERATES SparkovTxn samples for the property-fuzz
oracle.

The strategy draws across realistic feature ranges derived from the Step-1 data
analysis, deliberately INCLUDING the region the property-fuzz oracle needs to
expose the flawed detector: night-hour, risky-category frauds at LOW amount. The
declared `must_flag_when` invariant (risky_category_high_amount, see spec.yaml)
plus the night-hour rule mean such samples must be flagged; the amt-reliant
detector clears the low-amount ones, so a counterexample exists for the fuzzer
to find.

This lives with the victim (not the harness) so the oracle hardcodes no feature
names — the victim owns its sample shape and ranges, injected via wiring.
"""

from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy

from examples.targets.fraud_sparkov.record import SparkovTxn


def sparkov_strategy() -> SearchStrategy[SparkovTxn]:
    """Generate SparkovTxn across realistic ranges (amt 0-2000, hour 0-23, ...)."""
    return st.builds(
        SparkovTxn,
        txn_index=st.integers(min_value=0, max_value=10_000),
        amt=st.floats(
            min_value=0.0, max_value=2000.0, allow_nan=False, allow_infinity=False
        ),
        cat_risk=st.integers(min_value=0, max_value=1),
        hour=st.integers(min_value=0, max_value=23),
        age=st.integers(min_value=18, max_value=95),
        city_pop=st.integers(min_value=100, max_value=3_000_000),
        distance=st.floats(
            min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False
        ),
    )
