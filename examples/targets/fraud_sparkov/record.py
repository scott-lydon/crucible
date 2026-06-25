"""The opaque sample record for the real Sparkov fraud victim.

This is the victim-owned record the harness passes around as an opaque
``sample``. It carries a RICH, multi-signal feature set derived from the raw
23-column CSV (loader.py), so the detector reasons over real fraud signals — not
a 2-feature (amt + cat_risk) toy.

The fields fall into three groups:

* Static / contextual (the deployed victim USES these): ``amt``, ``cat_risk``,
  ``merchant_risk`` (per-merchant historical fraud rate, computed from the TRAIN
  split only), ``age``, ``city_pop``.
* Behavioral / temporal / geo (the deployed victim is BLIND to these — the
  realistic "we never engineered the behavioral features" gap): ``velocity``
  (prior txns on the same card in a recent window), ``day_of_week``,
  ``geo_distance_km`` (REAL haversine between cardholder and merchant).

The strong REFERENCE model (ground truth) uses ALL of them; the deployed victim
uses only the static/contextual ones; the cross-family second model uses the
rich set. That asymmetry — not a hardcoded rule — is the exploitable gap.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SparkovTxn:
    # Harness convention: every sample exposes a stable index.
    txn_index: int
    # --- Static / contextual signals (the deployed victim uses these) ------
    amt: float
    cat_risk: int  # 1 if category in the risky set, else 0
    merchant_risk: float  # per-merchant historical fraud rate (TRAIN split only)
    age: int
    city_pop: int
    # --- Behavioral / temporal / geo signals (the victim is BLIND to these) -
    # Prior transactions on the same card within VELOCITY_WINDOW_SECONDS.
    velocity: int = 0
    # Local hour-of-day of the transaction (0..23) — the night window carries a
    # strongly elevated real fraud rate.
    hour: int = 0
    # Day of week of the transaction (0=Monday .. 6=Sunday).
    day_of_week: int = 0
    # REAL haversine distance (km) between cardholder and merchant location.
    geo_distance_km: float = 0.0
