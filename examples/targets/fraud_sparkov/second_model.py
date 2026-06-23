"""A REAL second-family model: an unsupervised sklearn IsolationForest.

This is the independent cross-family opinion the differential oracle compares
the flawed LightGBM target against (constitution §1 / plan §3: "second
implementation from a different model family, require agreement").

Why a different family: the target is a gradient-boosted tree (LightGBM) fit
SUPERVISED on a deliberately narrow proxy set (``amt`` + ``cat_risk`` only).
The IsolationForest here is an UNSUPERVISED anomaly detector — a genuinely
different learning paradigm — fit on a RICHER feature set that INCLUDES the
``hour`` signal the flawed detector ignores. Because night-hour is the dominant
real fraud signal, the IsolationForest treats night-hour transactions (and
other off-distribution combinations) as anomalous and flags them even when the
amount has been lowered. That is exactly the amt-lowering night-hour evasion the
amount-reliant LightGBM clears, so the two families DISAGREE — and the
differential oracle catches it.

Feature set: ``amt, cat_risk, hour, age, city_pop`` — every interpretable field
the victim record (:class:`SparkovTxn`) exposes, crucially including ``hour``.
``distance`` is deliberately NOT used: the record carries no distance field and
the Step-1 analysis showed fraud/legit have an identical distance distribution
(pure noise; see record.py). Including a noise feature would only dilute the
anomaly signal, so the richer-than-the-target set stops at the features that
actually carry signal the target throws away (``hour``, plus the demographic
context ``age``/``city_pop``).

The artifact is gitignored (an external trained input, not source). Build it:
    python -m examples.targets.fraud_sparkov.second_model
"""

from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from examples.targets.fraud_sparkov.constants import TRAIN_CSV
from examples.targets.fraud_sparkov.loader import load_dataframe, verify_checksum
from examples.targets.fraud_sparkov.record import SparkovTxn

_RANDOM_STATE = 42

# Richer feature set than the flawed target's (amt, cat_risk): adds the night
# ``hour`` signal the target ignores, plus demographic context. Order is fixed
# and shared by training and scoring.
SECOND_MODEL_FEATURES: tuple[str, ...] = ("amt", "cat_risk", "hour", "age", "city_pop")

_HERE: Path = Path(__file__).resolve().parent
SECOND_MODEL_PATH: Path = _HERE / "artifacts" / "sparkov_isoforest.pkl"

# Cache the loaded estimator across scoring calls within a process.
_MODEL: IsolationForest | None = None


def _vector(sample: object) -> list[float]:
    """Build the IsolationForest feature vector off an opaque ``SparkovTxn``."""
    rec = sample if isinstance(sample, SparkovTxn) else None
    if rec is None:  # defensive: harness always passes SparkovTxn
        raise TypeError(
            f"second_model: expected SparkovTxn sample, got {type(sample).__name__}"
        )
    return [
        float(rec.amt),
        float(rec.cat_risk),
        float(rec.hour),
        float(rec.age),
        float(rec.city_pop),
    ]


def train_and_serialize(out_path: Path = SECOND_MODEL_PATH) -> IsolationForest:
    """Train the IsolationForest on the REAL Sparkov data and serialize it.

    Verifies the dataset checksum before training (external input guard). The
    fit is deterministic (seeded ``random_state``).
    """
    verify_checksum(TRAIN_CSV)
    df = load_dataframe(TRAIN_CSV, limit=None)
    x = df[list(SECOND_MODEL_FEATURES)].to_numpy(dtype=float)

    model = IsolationForest(
        n_estimators=100,
        max_samples=4096,
        # Anomaly band sized so the off-distribution night-hour region (only
        # ~23% of legit traffic is night, vs ~85% of real fraud) lands on the
        # anomalous side. Empirically catches ~half of the amt-lowered
        # night-hour evasions the amt-reliant LightGBM clears (see main()).
        contamination=0.15,
        random_state=_RANDOM_STATE,
        n_jobs=1,
    )
    model.fit(x)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out_path)
    return model


def _load_model() -> IsolationForest:
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    if not SECOND_MODEL_PATH.exists():
        raise FileNotFoundError(
            f"second_model: IsolationForest artifact not found at "
            f"'{SECOND_MODEL_PATH}'. It is a gitignored external input; build it "
            "with `python -m examples.targets.fraud_sparkov.second_model`."
        )
    model: IsolationForest = joblib.load(SECOND_MODEL_PATH)
    _MODEL = model
    return model


def isoforest_is_fraud(sample: object) -> bool:
    """Independent cross-family opinion: is ``sample`` anomalous (fraud)?

    Loads the serialized IsolationForest (cached) and returns ``True`` when it
    predicts the sample is an anomaly (``predict == -1``), else ``False``.
    """
    model = _load_model()
    vec = np.asarray([_vector(sample)], dtype=float)
    pred = int(model.predict(vec)[0])
    return pred == -1


def main() -> None:
    model = train_and_serialize()
    # Report whether the IsolationForest flags night-hour low-amt frauds that
    # the amount-reliant LightGBM clears — the cross-family catch.
    from examples.targets.fraud_sparkov.constants import NIGHT_HOURS

    df = load_dataframe(TRAIN_CSV, limit=None)
    night_fraud = df[(df["hour"].isin(list(NIGHT_HOURS))) & (df["is_fraud"] == 1)]
    # Simulate the amt-lowering evasion: drop amt to a low value the target clears.
    evaded = night_fraud.copy()
    evaded["amt"] = 12.0
    x = evaded[list(SECOND_MODEL_FEATURES)].to_numpy(dtype=float)
    preds = model.predict(x)
    flagged = int((preds == -1).sum())
    total = int(len(evaded))
    print("Sparkov second-family IsolationForest trained on REAL data.")
    print(f"  features: {list(SECOND_MODEL_FEATURES)} (includes night `hour`)")
    print(f"  serialized to: {SECOND_MODEL_PATH}")
    print(
        f"  night-hour frauds with amt lowered to 12.0 flagged as anomalous: "
        f"{flagged}/{total} ({(flagged / total * 100 if total else 0):.1f}%) "
        "— the cross-family catch the amt-reliant LightGBM misses."
    )


if __name__ == "__main__":
    main()
