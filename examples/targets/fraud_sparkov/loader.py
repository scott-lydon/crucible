"""Load REAL Sparkov rows into rich, multi-signal :class:`SparkovTxn` records.

This module derives the full rich feature menu with pandas and guards the
external CSVs against the committed ``dataset.sha256`` (fail-loud on mismatch —
the dataset is an external input, never source).

Derived signals (see record.py for the static/behavioral split):

* ``hour``, ``age``, ``day_of_week`` — from ``trans_date_trans_time`` / ``dob``.
* ``cat_risk`` — category-in-risky-set proxy.
* ``geo_distance_km`` — REAL haversine between cardholder (lat/long) and merchant
  (merch_lat/merch_long).
* ``velocity`` — prior transactions on the SAME card (``cc_num``) within
  ``VELOCITY_WINDOW_SECONDS`` (from ``unix_time``).
* ``merchant_risk`` — per-merchant historical fraud rate computed from the TRAIN
  split ONLY (no test-set leakage), applied to whatever split is loaded.

``merchant_risk`` is the one feature that needs a fitted lookup table. It is
computed once from the train CSV, cached, and reused so train/test/holdout all
see the same leak-free mapping.
"""

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from examples.targets.fraud_sparkov.constants import (
    CHECKSUM_PATH,
    RISKY_CATEGORIES,
    TRAIN_CSV,
    VELOCITY_WINDOW_SECONDS,
)
from examples.targets.fraud_sparkov.record import SparkovTxn

_EARTH_RADIUS_KM = 6371.0088

# Per-merchant fraud-rate lookup fitted on the TRAIN split, cached across calls.
# ``_MERCHANT_RISK`` maps merchant -> historical fraud rate; ``_MERCHANT_BASE``
# is the global train fraud rate, used for merchants unseen in training.
_MERCHANT_RISK: dict[str, float] | None = None
_MERCHANT_BASE: float = 0.0


def _expected_checksums() -> dict[str, str]:
    if not CHECKSUM_PATH.exists():
        raise FileNotFoundError(
            f"Sparkov: checksum manifest not found at '{CHECKSUM_PATH}'. "
            "It is committed source; restore it before loading data."
        )
    out: dict[str, str] = {}
    for line in CHECKSUM_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        digest, _, name = line.partition("  ")
        out[name.strip()] = digest.strip()
    return out


def verify_checksum(csv_path: str | Path) -> None:
    """Verify ``csv_path`` against the committed manifest. Raises on mismatch.

    The CSV basename must appear in ``dataset.sha256`` and its SHA-256 must
    match exactly. No silent pass for unknown files.
    """
    path = Path(csv_path)
    expected = _expected_checksums()
    name = path.name
    if name not in expected:
        raise ValueError(
            f"Sparkov: '{name}' is not listed in {CHECKSUM_PATH.name}; refusing "
            f"to load an unverified dataset (known: {sorted(expected)})."
        )
    if not path.exists():
        raise FileNotFoundError(
            f"Sparkov: dataset '{path}' not found. The CSVs are gitignored "
            "external inputs; place them under the victim's data/ directory."
        )
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != expected[name]:
        raise ValueError(
            f"Sparkov: checksum mismatch for '{name}'. "
            f"expected {expected[name]}, got {actual}. Dataset is corrupt or "
            "has been swapped; refusing to proceed."
        )


def _haversine_km(
    lat1: "pd.Series[float]",
    lon1: "pd.Series[float]",
    lat2: "pd.Series[float]",
    lon2: "pd.Series[float]",
) -> "pd.Series[float]":
    """Vectorized great-circle distance (km) between two lat/long columns."""
    rlat1, rlon1, rlat2, rlon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = np.sin(dlat / 2) ** 2 + np.cos(rlat1) * np.cos(rlat2) * np.sin(dlon / 2) ** 2
    return pd.Series(_EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a)))


def _velocity(df: pd.DataFrame) -> "pd.Series[int]":
    """Prior txns on the same card within VELOCITY_WINDOW_SECONDS.

    Sorts by card + time, then for each transaction counts how many earlier
    transactions on the SAME ``cc_num`` fall inside the trailing window. O(n log n)
    via a per-card two-pointer sweep over time-sorted rows.
    """
    order = df.sort_values(["cc_num", "unix_time"], kind="stable")
    times = order["unix_time"].to_numpy()
    cards = order["cc_num"].to_numpy()
    counts = np.zeros(len(order), dtype=np.int64)
    start = 0
    for i in range(len(order)):
        if i > 0 and cards[i] != cards[i - 1]:
            start = i  # new card: reset the window's left edge
        while times[i] - times[start] > VELOCITY_WINDOW_SECONDS:
            start += 1
        counts[i] = i - start  # earlier in-window txns on this card
    out = pd.Series(counts, index=order.index)
    return out.reindex(df.index)


def _fit_merchant_risk() -> tuple[dict[str, float], float]:
    """Fit the per-merchant fraud rate from the TRAIN split ONLY (cached)."""
    global _MERCHANT_RISK, _MERCHANT_BASE
    if _MERCHANT_RISK is not None:
        return _MERCHANT_RISK, _MERCHANT_BASE
    verify_checksum(TRAIN_CSV)
    train = pd.read_csv(TRAIN_CSV, usecols=["merchant", "is_fraud"])
    base = float(train["is_fraud"].mean())
    rates = train.groupby("merchant")["is_fraud"].mean()
    _MERCHANT_RISK = {str(k): float(v) for k, v in rates.items()}
    _MERCHANT_BASE = base
    return _MERCHANT_RISK, _MERCHANT_BASE


def load_dataframe(csv_path: str | Path, limit: int | None = None) -> pd.DataFrame:
    """Read the verified CSV and attach ALL derived rich-feature columns.

    The full rich menu (constants.RICH_FEATURES) plus the raw-derived ``hour``
    is materialized so train/score/holdout share identical derivations.
    """
    verify_checksum(csv_path)
    df = pd.read_csv(csv_path)
    # Explicit formats kill pandas' per-call format-inference warning and speed
    # the >1M-row parse. The Sparkov columns are fixed-shape.
    dt = pd.to_datetime(df["trans_date_trans_time"], format="%Y-%m-%d %H:%M:%S")
    dob = pd.to_datetime(df["dob"], format="%Y-%m-%d")
    df["hour"] = dt.dt.hour.astype(int)
    df["day_of_week"] = dt.dt.dayofweek.astype(int)
    df["age"] = ((dt - dob).dt.days // 365).astype(int)
    df["cat_risk"] = df["category"].isin(RISKY_CATEGORIES).astype(int)
    df["geo_distance_km"] = _haversine_km(
        df["lat"], df["long"], df["merch_lat"], df["merch_long"]
    ).round(4)
    df["velocity"] = _velocity(df).astype(int)
    merchant_risk, base = _fit_merchant_risk()
    df["merchant_risk"] = (
        df["merchant"].map(merchant_risk).fillna(base).astype(float).round(6)
    )
    if limit is not None:
        df = df.head(limit)
    return df


def _row_to_record(idx: int, row: "pd.Series[object]") -> SparkovTxn:
    return SparkovTxn(
        txn_index=idx,
        amt=round(float(row["amt"]), 2),
        cat_risk=int(row["cat_risk"]),
        merchant_risk=round(float(row["merchant_risk"]), 6),
        age=int(row["age"]),
        city_pop=int(row["city_pop"]),
        velocity=int(row["velocity"]),
        hour=int(row["hour"]),
        day_of_week=int(row["day_of_week"]),
        geo_distance_km=round(float(row["geo_distance_km"]), 4),
    )


def load_records(
    csv_path: str | Path = TRAIN_CSV,
    limit: int | None = None,
    seed: int = 0,
) -> list[SparkovTxn]:
    """Load REAL records as rich :class:`SparkovTxn`.

    When ``limit`` is set, a deterministic ``seed``-shuffled sample of ``limit``
    rows is returned (reproducible across runs).
    """
    df = load_dataframe(csv_path, limit=None)
    if limit is not None and limit < len(df):
        df = df.sample(n=limit, random_state=seed).reset_index(drop=True)
    return [_row_to_record(i, row) for i, (_, row) in enumerate(df.iterrows())]
