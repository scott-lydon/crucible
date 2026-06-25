"""A REAL second-family model: an unsupervised sklearn IsolationForest.

This is the independent cross-family opinion the differential oracle compares the
deployed LightGBM victim against (constitution §1 / plan §3: "second
implementation from a different model family, require agreement").

Why a different family: the victim is a SUPERVISED gradient-boosted tree
(LightGBM) fit on the static/contextual subset (``DETECTOR_FEATURES``). The
IsolationForest here is an UNSUPERVISED anomaly detector — a genuinely different
learning paradigm — fit on the FULL rich feature set (``RICH_FEATURES``), so it
SEES the behavioral/temporal/geo signals the victim is blind to (velocity,
day_of_week, geo_distance_km). When fraud manifests through those behavioral
axes, the IsolationForest treats the transaction as anomalous and flags it even
where the static-only victim clears it — exactly the disagreement the
differential oracle catches.

Feature set: ``RICH_FEATURES`` — the same rich menu the record carries and the
reference model uses. Keeping the second model's feature COUNT consistent with
the rich record (8 features) avoids the stale-artifact "N vs M" mismatch crashes;
training and scoring share ``RICH_FEATURES`` as the single point of truth.

The artifact is gitignored (an external trained input, not source). Build it:
    python -m examples.targets.fraud_sparkov.second_model
"""

from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from examples.targets.fraud_sparkov.constants import RICH_FEATURES, TRAIN_CSV
from examples.targets.fraud_sparkov.loader import load_dataframe, verify_checksum
from examples.targets.fraud_sparkov.record import SparkovTxn

_RANDOM_STATE = 42

# The cross-family model uses the FULL rich set (single point of truth shared by
# training and scoring) — crucially the behavioral/temporal/geo signals the
# static-only victim ignores.
SECOND_MODEL_FEATURES: tuple[str, ...] = RICH_FEATURES

_HERE: Path = Path(__file__).resolve().parent
SECOND_MODEL_PATH: Path = _HERE / "artifacts" / "sparkov_isoforest.pkl"

# Cache the loaded estimator across scoring calls within a process.
_MODEL: IsolationForest | None = None


def _vector(sample: object) -> list[float]:
    """Build the IsolationForest feature vector off an opaque ``SparkovTxn``."""
    if not isinstance(sample, SparkovTxn):  # defensive: harness passes SparkovTxn
        raise TypeError(
            f"second_model: expected SparkovTxn sample, got {type(sample).__name__}"
        )
    return [float(getattr(sample, name)) for name in SECOND_MODEL_FEATURES]


def train_and_serialize(out_path: Path = SECOND_MODEL_PATH) -> IsolationForest:
    """Train the IsolationForest on the REAL Sparkov data and serialize it.

    Verifies the dataset checksum before training (external-input guard). The fit
    is deterministic (seeded ``random_state``).
    """
    verify_checksum(TRAIN_CSV)
    df = load_dataframe(TRAIN_CSV, limit=None)
    x = df[list(SECOND_MODEL_FEATURES)].to_numpy(dtype=float)

    model = IsolationForest(
        n_estimators=100,
        max_samples=4096,
        # Anomaly band sized so off-distribution behavioral combinations (high
        # velocity, unusual geo distance, atypical day) land on the anomalous
        # side. These are precisely the axes the static-only victim ignores.
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
    train_and_serialize()
    print("Sparkov second-family IsolationForest trained on REAL data.")
    print(f"  features: {list(SECOND_MODEL_FEATURES)} (full rich set)")
    print(f"  serialized to: {SECOND_MODEL_PATH}")
    print(
        "  Sees the behavioral/temporal/geo signals the static-only victim "
        "ignores — the cross-family disagreement the differential oracle catches."
    )


if __name__ == "__main__":
    main()
