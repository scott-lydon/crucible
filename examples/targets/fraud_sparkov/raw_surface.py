"""Victim RAW surface — the data a genuine maker actually has.

The blue code-engineering agent (``modules/blue/code_engineer.py``, Option B)
does NOT get the derived feature menu (``hour``/``distance``/``age``). It gets
only the RAW Sparkov CSV columns and must DISCOVER the missing signal from them
by writing a feature-engineering transform. This module is the victim-owned raw
surface that the composition root (``orchestrator/wiring.py``) injects:

* ``RAW_COLUMNS`` — the raw column names a maker has (no derived columns).
* ``load_raw_rows`` — REAL raw CSV rows as plain dicts (checksum-verified), each
  carrying the raw columns PLUS the model's CURRENT base features (``amt`` is
  raw; ``cat_risk`` is a trivial victim-owned base proxy) and the ``is_fraud``
  label, so the harness can retrain and validate without re-deriving anything.
* ``load_holdout_raw_rows`` — the held-out evasions as RAW rows: real night-hour
  frauds with ``amt`` lowered (the exact metamorphic evasion the red loop lands),
  which the amt-reliant deployed detector clears and a real ``hour``-engineering
  maker can recover. Raw so the maker's transform runs over the SAME schema.
* ``retrain_with_engineered`` — retrain a LightGBM on the model's CURRENT base
  features PLUS one engineered column (the values produced by the maker's
  sandboxed transform), returning a ``Detector`` whose ``.score`` re-applies the
  same trusted ``engineer`` callable to compute the engineered value at scoring
  time. Trusted, in-process.

This is ADDITIVE: the derived ``SparkovTxn``/detector used by the red loop is
unchanged. Only blue's Option-B path consumes the raw surface.
"""

import hashlib
from collections.abc import Callable, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import joblib
import lightgbm as lgb
import pandas as pd
from lightgbm import Booster

from examples.targets.fraud_sparkov.constants import (
    DETECTOR_FEATURES,
    RISKY_CATEGORIES,
    TRAIN_CSV,
)
from examples.targets.fraud_sparkov.loader import load_dataframe

# Held-out evasion construction: real frauds in the night window with a non-trivial
# amount, whose amount we lower (label preserved) so the amount-sensitive,
# behavior/time-blind victim clears them. A maker who engineers the temporal
# ``hour`` signal from the raw timestamp recovers them. These thresholds are local
# to the raw-surface holdout (the deployed detector no longer uses an hour rule).
_HOLDOUT_NIGHT_HOURS: frozenset[int] = frozenset({22, 23, 0, 1, 2, 3})
_HOLDOUT_AMT_HIGH: float = 250.0

_RANDOM_STATE = 42
_HERE: Path = Path(__file__).resolve().parent
_ARTIFACTS: Path = _HERE / "artifacts"

# The RAW Sparkov CSV columns a maker actually has. NO derived hour/distance/age:
# the maker must engineer those from these raw columns to recover the signal.
RAW_COLUMNS: tuple[str, ...] = (
    "trans_date_trans_time",
    "cc_num",
    "merchant",
    "category",
    "amt",
    "gender",
    "lat",
    "long",
    "city_pop",
    "job",
    "dob",
    "unix_time",
    "merch_lat",
    "merch_long",
)

# The model's CURRENT base features (single point of truth: the victim
# constants). ``amt``/``city_pop`` are raw columns; ``cat_risk`` is the victim's
# category-risk base proxy; ``merchant_risk`` is the per-merchant historical fraud
# rate and ``age`` is derived from dob/txn-time — all carried on every raw row so
# the harness can retrain the base model without re-deriving them. The BLIND
# signals (velocity / hour / day_of_week / geo) are NOT here — that is precisely
# the gap the maker must discover and engineer from the raw columns.
BASE_FEATURES: tuple[str, ...] = tuple(DETECTOR_FEATURES)


def _cat_risk(category: object) -> int:
    return 1 if str(category) in RISKY_CATEGORIES else 0


def _row_dict(idx: int, row: "pd.Series[object]") -> dict[str, object]:
    """One raw row as a plain dict: raw columns + base features + label.

    Carries every ``RAW_COLUMNS`` value plus all of ``BASE_FEATURES``
    (amt, cat_risk, merchant_risk, age, city_pop) so the harness can retrain the
    base model and re-score the holdout without re-deriving the base features.
    """
    out: dict[str, object] = {col: row[col] for col in RAW_COLUMNS}
    # Coerce the numeric raw columns to plain Python floats so the dict is
    # JSON-serializable for the sandbox transport (no numpy scalars).
    for num in ("amt", "lat", "long", "city_pop", "unix_time", "merch_lat", "merch_long"):
        out[num] = float(row[num])
    out["txn_index"] = idx
    out["cat_risk"] = _cat_risk(row["category"])  # base proxy, carried for retrain
    # The remaining base features are derived by the loader (merchant_risk from the
    # train split, age from dob); carry them so the base model retrains cleanly.
    out["merchant_risk"] = round(float(row["merchant_risk"]), 6)
    out["age"] = int(row["age"])
    out["is_fraud"] = int(row["is_fraud"])
    return out


def load_raw_rows(limit: int | None = None, seed: int = 0) -> list[dict[str, object]]:
    """Load REAL Sparkov rows as raw dicts (checksum-verified via the loader).

    Each dict carries every ``RAW_COLUMNS`` value plus the base features
    (``amt``/``cat_risk``), a stable ``txn_index``, and ``is_fraud``. A
    deterministic ``seed``-shuffled sample of ``limit`` rows is returned when
    ``limit`` is set (reproducible across runs).
    """
    df = load_dataframe(TRAIN_CSV, limit=None)
    if limit is not None and limit < len(df):
        df = df.sample(n=limit, random_state=seed).reset_index(drop=True)
    return [_row_dict(i, row) for i, (_, row) in enumerate(df.iterrows())]


def load_holdout_raw_rows(
    limit: int = 200, seed: int = 0, evade_factor: float = 0.5
) -> list[SimpleNamespace]:
    """Held-out evasions as RAW samples: real night-frauds with ``amt`` lowered.

    Mirrors the metamorphic evasion the red loop lands — a genuine fraud (per the
    real committed ``is_fraud`` label) whose ``amt`` is scaled by
    ``evade_factor`` (the mutator's gentlest 0.5 ladder rung), enough to drop the
    high-amount fraud below the amt-reliant detector's bar while leaving a real,
    non-trivial amount the engineered night-hour feature can still flag. The label
    is preserved (``is_fraud`` stays 1). Returned as attribute-bearing
    ``SimpleNamespace`` samples carrying the SAME raw schema as training (so the
    OLD attribute-based detector can score them AND the maker's transform reads
    them via ``vars()``); ``hour`` is NOT present (must be engineered from
    ``trans_date_trans_time``).
    """
    df = load_dataframe(TRAIN_CSV, limit=None)
    night = df[
        (df["hour"].isin(list(_HOLDOUT_NIGHT_HOURS)))
        & (df["amt"] > _HOLDOUT_AMT_HIGH)
        & (df["is_fraud"] == 1)
    ]
    if limit < len(night):
        night = night.sample(n=limit, random_state=seed).reset_index(drop=True)
    out: list[SimpleNamespace] = []
    for i, (_, row) in enumerate(night.iterrows()):
        d = _row_dict(i, row)
        # The amt-lowering evasion (label preserved): scale the high amount down.
        d["amt"] = round(float(row["amt"]) * evade_factor, 2)
        out.append(SimpleNamespace(**d))
    return out


def raw_is_fraud(sample: object) -> bool:
    """Ground-truth label for a RAW row dict (carries the real ``is_fraud``).

    The blue maker validates recovery on raw rows that have no derived ``hour``,
    so the derived ``is_fraud`` rule cannot read them. The raw rows carry the
    REAL committed label instead — this reads it directly. Used as the blue
    loop's ``label_fn`` over the raw holdout.
    """
    row = sample if isinstance(sample, dict) else vars(sample)
    return int(row.get("is_fraud", 0)) == 1


def _features_hash(feature_names: Sequence[str]) -> str:
    return hashlib.sha256(",".join(feature_names).encode()).hexdigest()[:12]


class EngineeredDetector:
    """A ``Detector`` over base features + ONE engineered column.

    Scores a raw-dict sample by reading the base features off the dict and
    re-applying the trusted ``engineer`` callable to compute the engineered
    value in-process. The engineer was VETTED in the Docker sandbox during
    discovery; the harness owns its re-execution at scoring time (the sandbox is
    the untrusted-execution gate, not a per-score requirement).
    """

    def __init__(
        self,
        booster: Booster,
        base_features: Sequence[str],
        engineer: Callable[[dict[str, object]], float],
    ) -> None:
        self._booster = booster
        self._base_features = tuple(base_features)
        self._engineer = engineer

    def _vector(self, sample: object) -> list[float]:
        row = sample if isinstance(sample, dict) else vars(sample)
        vec = [float(row[name]) for name in self._base_features]
        vec.append(float(self._engineer(row)))
        return vec

    def score(self, sample: object) -> float:
        proba = self._booster.predict([self._vector(sample)])
        return float(proba[0])


def retrain_with_engineered(
    raw_rows: Sequence[dict[str, object]],
    engineered_values: Sequence[float],
    base_feature_names: Sequence[str],
    engineer: Callable[[dict[str, object]], float],
    seed: int = _RANDOM_STATE,
) -> EngineeredDetector:
    """Retrain a LightGBM on base features + the maker's engineered column.

    ``engineered_values`` are the sandbox-produced transform outputs aligned to
    ``raw_rows`` (the harness, not the maker, supplied the I/O). Trains
    deterministically on ``[*base_features, engineered]``, serializes the bare
    Booster (gitignored artifact), and returns an :class:`EngineeredDetector`
    that re-applies ``engineer`` to score the holdout. Trusted, in-process.
    """
    base = list(base_feature_names)
    if not base:
        raise ValueError("retrain_with_engineered: base_feature_names must be non-empty.")
    if len(engineered_values) != len(raw_rows):
        raise ValueError(
            "retrain_with_engineered: engineered_values length "
            f"{len(engineered_values)} != raw_rows length {len(raw_rows)}."
        )

    x = [
        [float(cast(float, row[name])) for name in base]
        + [float(engineered_values[i])]
        for i, row in enumerate(raw_rows)
    ]
    y = [int(cast(int, row["is_fraud"])) for row in raw_rows]

    clf = lgb.LGBMClassifier(
        n_estimators=200,
        num_leaves=15,
        learning_rate=0.05,
        scale_pos_weight=10,
        random_state=seed,
        n_jobs=1,
        verbose=-1,
        deterministic=True,
        force_col_wise=True,
    )
    clf.fit(x, y)
    booster: Booster = clf.booster_

    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out_path = _ARTIFACTS / f"sparkov_blueB_{_features_hash([*base, 'engineered'])}.lgb"
    joblib.dump(booster, out_path)
    return EngineeredDetector(booster, base, engineer)
