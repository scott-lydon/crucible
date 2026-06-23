"""REAL Sparkov fraud victim (slice-2).

A flawed, amount-reliant LightGBM detector trained on the real Sparkov dataset,
a declared interpretable ground-truth rule, and a SealedSpec the oracles read.
Only orchestrator/wiring.py (the composition root) may import from here.
"""

from examples.targets.fraud_sparkov.constants import (
    AMT_HIGH,
    BATCH_FRAUD_RATE,
    DETECTOR_FEATURES,
    DETECTOR_THRESHOLD,
    MODEL_PATH,
    NIGHT_HOURS,
    RISKY_CATEGORIES,
)
from examples.targets.fraud_sparkov.generator import generate_batch
from examples.targets.fraud_sparkov.loader import (
    load_dataframe,
    load_records,
    verify_checksum,
)
from examples.targets.fraud_sparkov.record import SparkovTxn
from examples.targets.fraud_sparkov.rule import is_fraud
from examples.targets.fraud_sparkov.second_model import (
    SECOND_MODEL_FEATURES,
    SECOND_MODEL_PATH,
    isoforest_is_fraud,
)
from examples.targets.fraud_sparkov.spec import SPEC_PATH, load_spec

__all__ = [
    "AMT_HIGH",
    "BATCH_FRAUD_RATE",
    "DETECTOR_FEATURES",
    "DETECTOR_THRESHOLD",
    "MODEL_PATH",
    "NIGHT_HOURS",
    "RISKY_CATEGORIES",
    "SECOND_MODEL_FEATURES",
    "SECOND_MODEL_PATH",
    "SPEC_PATH",
    "SparkovTxn",
    "generate_batch",
    "is_fraud",
    "isoforest_is_fraud",
    "load_dataframe",
    "load_records",
    "load_spec",
    "verify_checksum",
]
