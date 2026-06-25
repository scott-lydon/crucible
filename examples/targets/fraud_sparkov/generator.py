"""Deterministic batch generator over the REAL Sparkov test data.

Implements the harness ``GenerateFn`` signature ``(seed: str, size: int)``.
Returns a reproducible, class-balanced sample of REAL rich records (re-indexed
with ``txn_index``). The fraud half is drawn from rows the REAL dataset marks
``is_fraud == 1`` with a non-trivial amount, so the metamorphic adversary has
true-positives whose amount it can lower (label preserved, judged by the strong
reference model) to probe the behavior-blind victim.

Ground truth is now the reference model (``reference_is_fraud``), not a
night-hour rule — but the generator selects by the committed REAL ``is_fraud``
label (cheap, no model load) for a credible balanced batch; the oracles apply
the reference-model label at verdict time.
"""

import hashlib
import random

from examples.targets.fraud_sparkov.constants import BATCH_FRAUD_RATE, TEST_CSV
from examples.targets.fraud_sparkov.loader import load_dataframe
from examples.targets.fraud_sparkov.record import SparkovTxn

# Minimum amount for an "attackable" fraud: enough that the amt-decrease ladder
# has room to move it under the victim's bar while staying a real amount.
_ATTACKABLE_MIN_AMT = 100.0

# Cache the parsed records across calls (verification + parse is expensive).
_CACHE: dict[str, tuple[list[SparkovTxn], list[SparkovTxn]]] = {}


def _seed_int(seed: str) -> int:
    return int(hashlib.sha256(seed.encode()).hexdigest(), 16)


def _record(idx: int, row: object) -> SparkovTxn:
    r = row  # pandas Series, indexed by column name
    return SparkovTxn(
        txn_index=idx,
        amt=round(float(r["amt"]), 2),  # type: ignore[index]
        cat_risk=int(r["cat_risk"]),  # type: ignore[index]
        merchant_risk=round(float(r["merchant_risk"]), 6),  # type: ignore[index]
        age=int(r["age"]),  # type: ignore[index]
        city_pop=int(r["city_pop"]),  # type: ignore[index]
        velocity=int(r["velocity"]),  # type: ignore[index]
        hour=int(r["hour"]),  # type: ignore[index]
        day_of_week=int(r["day_of_week"]),  # type: ignore[index]
        geo_distance_km=round(float(r["geo_distance_km"]), 4),  # type: ignore[index]
    )


def _pools() -> tuple[list[SparkovTxn], list[SparkovTxn]]:
    """Return (attackable_frauds, legit) record pools from the test split."""
    key = str(TEST_CSV)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    df = load_dataframe(TEST_CSV, limit=None)
    fraud_df = df[(df["is_fraud"] == 1) & (df["amt"] >= _ATTACKABLE_MIN_AMT)]
    legit_df = df[df["is_fraud"] == 0]
    attackable = [_record(i, row) for i, (_, row) in enumerate(fraud_df.iterrows())]
    legit = [_record(i, row) for i, (_, row) in enumerate(legit_df.iterrows())]
    _CACHE[key] = (attackable, legit)
    return attackable, legit


def generate_batch(seed: str, size: int) -> list[SparkovTxn]:
    rng = random.Random(_seed_int(seed))
    attackable, legit = _pools()

    n_fraud = int(size * BATCH_FRAUD_RATE)
    n_legit = size - n_fraud
    chosen_fraud = rng.sample(attackable, k=min(n_fraud, len(attackable)))
    chosen_legit = rng.sample(legit, k=min(n_legit, len(legit)))

    combined = chosen_fraud + chosen_legit
    rng.shuffle(combined)
    # Re-index so txn_index is the batch position (harness convention).
    return [
        SparkovTxn(
            txn_index=i,
            amt=r.amt,
            cat_risk=r.cat_risk,
            merchant_risk=r.merchant_risk,
            age=r.age,
            city_pop=r.city_pop,
            velocity=r.velocity,
            hour=r.hour,
            day_of_week=r.day_of_week,
            geo_distance_km=r.geo_distance_km,
        )
        for i, r in enumerate(combined)
    ]
