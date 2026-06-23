"""Tunable constants for the Sparkov victim, all derived from the Step-1
analysis over the REAL fraudTrain.csv (see the build report for the numbers).
"""

from pathlib import Path

# --- Declared ground-truth rule thresholds -------------------------------
# Night window (local hour) where the real data shows a ~2.1% fraud rate vs
# ~0.12% in daytime; 84.8% of real frauds fall here.
NIGHT_HOURS: frozenset[int] = frozenset({22, 23, 0, 1, 2, 3})
# Categories with elevated fraud rate (shopping_net 1.76%, misc_net 1.45%,
# grocery_pos 1.41%, shopping_pos 0.72% vs ~0.58% base rate).
RISKY_CATEGORIES: frozenset[str] = frozenset(
    {"shopping_net", "misc_net", "grocery_pos", "shopping_pos"}
)
# High-amount cut for the risky-category arm of the rule. Real fraud median
# amt is ~396 vs ~47 legit; 250 sits below the fraud mass, above legit.
AMT_HIGH: float = 250.0

# --- Detector / batch ------------------------------------------------------
DETECTOR_THRESHOLD: float = 0.5
# Fraction of forced frauds in a generated batch (the real base rate is ~0.6%;
# we oversample so the red loop has true-positives to attack).
BATCH_FRAUD_RATE: float = 0.5

# --- Artifact + data locations (victim-relative) ---------------------------
_HERE: Path = Path(__file__).resolve().parent
MODEL_FILENAME: str = "sparkov_flawed.pkl"
MODEL_PATH: Path = _HERE / "artifacts" / MODEL_FILENAME
TRAIN_CSV: Path = _HERE / "data" / "fraudTrain.csv"
TEST_CSV: Path = _HERE / "data" / "fraudTest.csv"
CHECKSUM_PATH: Path = _HERE / "dataset.sha256"

# Feature order the LocalModelTarget feeds the serialized model. The flawed
# detector is trained ONLY on these proxies (no hour, no distance) — that is
# the exploitable gap.
DETECTOR_FEATURES: tuple[str, ...] = ("amt", "cat_risk")
