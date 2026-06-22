"""Real fraud data loading and the sealed three-way split.

Source is the ULB Credit Card Fraud dataset (OpenML data_id 1597 — the public mirror
of the Kaggle set; no Kaggle credentials needed). The split is deterministic and
stratified so the 0.172% fraud rate is preserved in every partition:

* ``train``   — the producer (LightGBM) trains on this.
* ``holdout`` — the held-out oracle (slice 5) scores against this; the producer
  NEVER sees it (the held-out firewall, constitution.md section 3).
* ``eval``    — slice-2 AUC is measured here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pandas as pd
from sklearn.datasets import fetch_openml
from sklearn.model_selection import train_test_split

REPO = Path(__file__).resolve().parents[3]
CSV_PATH = REPO / "data" / "creditcard.csv"
OPENML_DATA_ID = 1597
TARGET_COLUMN = "Class"
SPLIT_SEED = 42


@dataclass(frozen=True, slots=True)
class FraudSplits:
    x_train: pd.DataFrame
    y_train: pd.Series
    x_holdout: pd.DataFrame
    y_holdout: pd.Series
    x_eval: pd.DataFrame
    y_eval: pd.Series
    feature_names: list[str]
    data_sha256: str


def load_dataframe() -> pd.DataFrame:
    """Load the dataset, preferring the checksummed local CSV (risk spike cr-r1),
    falling back to the OpenML mirror. Fails loud if neither is reachable."""
    if CSV_PATH.exists():
        return cast("pd.DataFrame", pd.read_csv(CSV_PATH))
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    bunch = fetch_openml(data_id=OPENML_DATA_ID, as_frame=True, parser="auto")
    frame = cast("pd.DataFrame", bunch.frame)
    frame.to_csv(CSV_PATH, index=False)
    return frame


def _sha256_frame(frame: pd.DataFrame) -> str:
    payload = pd.util.hash_pandas_object(frame, index=True).values.tobytes()
    return hashlib.sha256(payload).hexdigest()


def load_splits() -> FraudSplits:
    frame = load_dataframe()
    target = TARGET_COLUMN if TARGET_COLUMN in frame.columns else frame.columns[-1]
    features = [c for c in frame.columns if c != target]
    x = frame[features]
    y = frame[target].astype(int)

    x_train, x_temp, y_train, y_temp = train_test_split(
        x, y, test_size=0.30, random_state=SPLIT_SEED, stratify=y
    )
    x_holdout, x_eval, y_holdout, y_eval = train_test_split(
        x_temp, y_temp, test_size=0.50, random_state=SPLIT_SEED, stratify=y_temp
    )
    return FraudSplits(
        x_train=x_train, y_train=y_train,
        x_holdout=x_holdout, y_holdout=y_holdout,
        x_eval=x_eval, y_eval=y_eval,
        feature_names=list(features),
        data_sha256=_sha256_frame(frame),
    )
