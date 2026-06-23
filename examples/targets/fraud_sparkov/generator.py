"""Deterministic batch generator over the REAL Sparkov test data.

Implements the harness ``GenerateFn`` signature ``(seed: str, size: int)``.
Returns a reproducible, class-balanced sample of REAL records (re-indexed with
``txn_index``). The fraud half is biased toward *attackable* night-frauds with
high amount: these are fraud because of the night hour, so the metamorphic
adversary can lower ``amt`` (label preserved) and slip past the amt-reliant
flawed detector — the genuine evasion story the analysis confirmed.
"""

import hashlib
import random

from examples.targets.fraud_sparkov.constants import (
    AMT_HIGH,
    BATCH_FRAUD_RATE,
    NIGHT_HOURS,
    TEST_CSV,
)
from examples.targets.fraud_sparkov.loader import load_dataframe
from examples.targets.fraud_sparkov.record import SparkovTxn
from examples.targets.fraud_sparkov.rule import is_fraud

# Cache the parsed dataframe across calls (verification + parse is expensive).
_CACHE: dict[str, list[SparkovTxn]] = {}


def _seed_int(seed: str) -> int:
    return int(hashlib.sha256(seed.encode()).hexdigest(), 16)


def _all_records() -> list[SparkovTxn]:
    key = str(TEST_CSV)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    df = load_dataframe(TEST_CSV, limit=None)
    recs: list[SparkovTxn] = []
    for i, (_, row) in enumerate(df.iterrows()):
        recs.append(
            SparkovTxn(
                txn_index=i,
                amt=round(float(row["amt"]), 2),
                cat_risk=int(row["cat_risk"]),
                hour=int(row["hour"]),
                age=int(row["age"]),
                city_pop=int(row["city_pop"]),
            )
        )
    _CACHE[key] = recs
    return recs


def generate_batch(seed: str, size: int) -> list[SparkovTxn]:
    rng = random.Random(_seed_int(seed))
    pool = _all_records()

    # Attackable frauds: night-hour AND high amount -> caught by amt-detector,
    # but lowering amt preserves the (night-driven) fraud label.
    attackable = [
        r
        for r in pool
        if r.hour in NIGHT_HOURS and r.amt > AMT_HIGH and is_fraud(r)
    ]
    legit = [r for r in pool if not is_fraud(r)]

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
            hour=r.hour,
            age=r.age,
            city_pop=r.city_pop,
        )
        for i, r in enumerate(combined)
    ]
