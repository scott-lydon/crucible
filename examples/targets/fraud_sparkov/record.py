"""The opaque sample record for the real Sparkov fraud victim.

This is the victim-owned record the harness passes around as an opaque
``sample``. It carries only the interpretable, derived features the declared
rule and the flawed detector reason over — never the raw 23-column CSV row.

The field set is chosen from the Step-1 data analysis (see the build report):
``hour`` (night-hour is the dominant fraud signal, 84.8% of real frauds),
``amt`` and ``cat_risk`` (the proxies the flawed detector over-relies on),
plus ``age``/``city_pop`` carried for transparency. ``distance_km`` is
deliberately NOT a feature: the real data shows fraud and legit have an
identical distance distribution (median ~78km for both), so it is pure noise.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SparkovTxn:
    # Harness convention: every sample exposes a stable index.
    txn_index: int
    # Proxies the flawed detector leans on.
    amt: float
    cat_risk: int  # 1 if category in the risky set, else 0
    # The strong causal signal the flawed detector under-uses.
    hour: int
    # Carried for transparency / interpretability of the rule.
    age: int
    city_pop: int
