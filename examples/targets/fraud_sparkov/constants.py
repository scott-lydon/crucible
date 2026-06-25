"""Tunable constants for the Sparkov victim.

Part B1 rework: the victim is no longer a 2-feature (amt + cat_risk) toy judged
by a night-hour rule. The ground truth is now a strong LightGBM REFERENCE model
trained on the full rich feature set (see ``reference_model.py``); the deployed
VICTIM is a realistic multi-feature detector that is deliberately BLIND to a
believable SET of behavioral/temporal/geo signals (see ``train.py``). The
night-hour rule and its constants are retired.
"""

from pathlib import Path

# --- Categories with elevated fraud rate ----------------------------------
# Used only to derive the trivial ``cat_risk`` base proxy (one of several
# signals now). shopping_net 1.76%, misc_net 1.45%, grocery_pos 1.41%,
# shopping_pos 0.72% vs ~0.58% base rate.
RISKY_CATEGORIES: frozenset[str] = frozenset(
    {"shopping_net", "misc_net", "grocery_pos", "shopping_pos"}
)

# --- Velocity window -------------------------------------------------------
# How far back (seconds) to count prior transactions on the same card when
# deriving the ``velocity`` behavioral signal. 1h: a card seeing several
# transactions within an hour is a classic fraud-burst signal. In the REAL data
# this is strong — ~43% of frauds have a prior same-card txn within the hour vs
# ~16% of legit (see the build report), so a victim blind to velocity has a real,
# recoverable gap (not the old night-hour toy).
VELOCITY_WINDOW_SECONDS: int = 3600

# --- Detector / batch ------------------------------------------------------
DETECTOR_THRESHOLD: float = 0.5
# Reference-model decision threshold: a transaction is ground-truth fraud when
# the reference model's predicted fraud probability exceeds this. Calibrated in
# ``reference_model.py`` (reported alongside its held-out AUC); 0.5 is the
# default operating point for the balanced (scale_pos_weight) classifier.
REFERENCE_THRESHOLD: float = 0.5
# Fraction of forced frauds in a generated batch (the real base rate is ~0.6%;
# we oversample so the red loop has true-positives to attack).
BATCH_FRAUD_RATE: float = 0.5

# --- Artifact + data locations (victim-relative) ---------------------------
_HERE: Path = Path(__file__).resolve().parent
MODEL_FILENAME: str = "sparkov_flawed.pkl"
MODEL_PATH: Path = _HERE / "artifacts" / MODEL_FILENAME
REFERENCE_MODEL_PATH: Path = _HERE / "artifacts" / "sparkov_reference.pkl"
TRAIN_CSV: Path = _HERE / "data" / "fraudTrain.csv"
TEST_CSV: Path = _HERE / "data" / "fraudTest.csv"
CHECKSUM_PATH: Path = _HERE / "dataset.sha256"

# --- Feature sets ----------------------------------------------------------
# The FULL rich feature menu derived per transaction (loader.py / record.py).
# Order is the single point of truth shared by training and scoring. It spans
# static/contextual, behavioral, temporal, and geo signals so the reference model
# trained on it is genuinely strong.
RICH_FEATURES: tuple[str, ...] = (
    "amt",
    "cat_risk",
    "merchant_risk",
    "age",
    "city_pop",
    "velocity",
    "hour",
    "day_of_week",
    "geo_distance_km",
)

# The deployed VICTIM detector's feature set. It uses the static/contextual
# signals (amount, category risk, per-merchant historical risk, demographics)
# but is deliberately BLIND to the BEHAVIORAL/TEMPORAL/GEO signals — a plausible
# "we never engineered the behavioral/time/geo features" gap, not a 2-feature
# toy. The blind SET is exactly RICH_FEATURES minus these.
DETECTOR_FEATURES: tuple[str, ...] = (
    "amt",
    "cat_risk",
    "merchant_risk",
    "age",
    "city_pop",
)

# The signals the deployed victim is blind to (RICH_FEATURES - DETECTOR_FEATURES):
# behavioral (velocity), temporal (hour, day_of_week), geo (geo_distance_km). The
# red loop exploits this set; the blue loop closes it by engineering them back in.
# velocity and hour carry the strongest real signal here.
BLIND_FEATURES: tuple[str, ...] = (
    "velocity",
    "hour",
    "day_of_week",
    "geo_distance_km",
)
