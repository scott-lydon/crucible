"""Load REAL Sparkov rows into interpretable :class:`SparkovTxn` records.

Computes derived features (hour-of-day, age-from-dob, cat_risk) with pandas.
``verify_checksum`` guards the external CSVs against the committed
``dataset.sha256`` and fails loud on any mismatch — the dataset is an external
input, never source.
"""

import hashlib
from pathlib import Path

import pandas as pd

from examples.targets.fraud_sparkov.constants import (
    CHECKSUM_PATH,
    RISKY_CATEGORIES,
    TRAIN_CSV,
)
from examples.targets.fraud_sparkov.record import SparkovTxn


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


def load_dataframe(csv_path: str | Path, limit: int | None = None) -> pd.DataFrame:
    """Read the verified CSV and attach the derived interpretable columns."""
    verify_checksum(csv_path)
    df = pd.read_csv(csv_path)
    dt = pd.to_datetime(df["trans_date_trans_time"])
    dob = pd.to_datetime(df["dob"])
    df["hour"] = dt.dt.hour.astype(int)
    df["age"] = ((dt - dob).dt.days // 365).astype(int)
    df["cat_risk"] = df["category"].isin(RISKY_CATEGORIES).astype(int)
    if limit is not None:
        df = df.head(limit)
    return df


def _row_to_record(idx: int, row: "pd.Series[object]") -> SparkovTxn:
    return SparkovTxn(
        txn_index=idx,
        amt=round(float(row["amt"]), 2),
        cat_risk=int(row["cat_risk"]),
        hour=int(row["hour"]),
        age=int(row["age"]),
        city_pop=int(row["city_pop"]),
    )


def load_records(
    csv_path: str | Path = TRAIN_CSV,
    limit: int | None = None,
    seed: int = 0,
) -> list[SparkovTxn]:
    """Load REAL records as :class:`SparkovTxn`.

    When ``limit`` is set, a deterministic ``seed``-shuffled sample of ``limit``
    rows is returned (reproducible across runs).
    """
    df = load_dataframe(csv_path, limit=None)
    if limit is not None and limit < len(df):
        df = df.sample(n=limit, random_state=seed).reset_index(drop=True)
    return [_row_to_record(i, row) for i, (_, row) in enumerate(df.iterrows())]
