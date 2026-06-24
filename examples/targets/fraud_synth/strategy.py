"""Hypothesis strategy that GENERATES Transaction samples for the property-fuzz
oracle on the synthetic victim.

Ranges span the declared `must_flag_when` invariant (country_mismatch true AND
velocity > 5) so the fuzzer can find a generated transaction that satisfies it
yet the amount-reliant flawed detector clears — keeping the synth fixture at the
full 6-oracle complement. The victim owns its sample shape; the harness stays
target-agnostic.
"""

from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy

from examples.targets.fraud_synth.transaction import Transaction


def synth_strategy() -> SearchStrategy[Transaction]:
    """Generate Transaction across realistic ranges."""
    return st.builds(
        Transaction,
        txn_index=st.integers(min_value=0, max_value=10_000),
        amount=st.floats(
            min_value=0.0, max_value=2000.0, allow_nan=False, allow_infinity=False
        ),
        velocity=st.integers(min_value=0, max_value=30),
        country_mismatch=st.booleans(),
        merchant_risk=st.floats(
            min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
        ),
        hour_of_day=st.integers(min_value=0, max_value=23),
    )
