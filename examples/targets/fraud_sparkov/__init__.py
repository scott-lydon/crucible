"""REAL Sparkov fraud victim (Part B1: multi-signal rework).

A realistic multi-feature LightGBM detector trained on the real Sparkov dataset
(blind to a believable SET of behavioral/temporal/geo signals), a strong
multi-signal REFERENCE model that serves as the ground-truth proxy, and a
SealedSpec the oracles read. Only orchestrator/wiring.py (the composition root)
may import from here.
"""

from examples.targets.fraud_sparkov.constants import (
    BATCH_FRAUD_RATE,
    BLIND_FEATURES,
    DETECTOR_FEATURES,
    DETECTOR_THRESHOLD,
    MODEL_PATH,
    REFERENCE_MODEL_PATH,
    REFERENCE_THRESHOLD,
    RICH_FEATURES,
    RISKY_CATEGORIES,
)
from examples.targets.fraud_sparkov.generator import generate_batch
from examples.targets.fraud_sparkov.loader import (
    load_dataframe,
    load_records,
    verify_checksum,
)
from examples.targets.fraud_sparkov.raw_surface import (
    BASE_FEATURES,
    RAW_COLUMNS,
    EngineeredDetector,
    load_holdout_raw_rows,
    load_raw_rows,
    raw_is_fraud,
    retrain_with_engineered,
)
from examples.targets.fraud_sparkov.record import SparkovTxn
from examples.targets.fraud_sparkov.reference_model import reference_is_fraud
from examples.targets.fraud_sparkov.retrain import (
    AVAILABLE_FEATURES,
    CURRENT_FEATURES,
    retrain_with_features,
)
from examples.targets.fraud_sparkov.rule import is_fraud
from examples.targets.fraud_sparkov.second_model import (
    SECOND_MODEL_FEATURES,
    SECOND_MODEL_PATH,
    isoforest_is_fraud,
)
from examples.targets.fraud_sparkov.spec import SPEC_PATH, load_spec
from examples.targets.fraud_sparkov.strategy import sparkov_strategy

__all__ = [
    "AVAILABLE_FEATURES",
    "BASE_FEATURES",
    "BATCH_FRAUD_RATE",
    "BLIND_FEATURES",
    "CURRENT_FEATURES",
    "DETECTOR_FEATURES",
    "DETECTOR_THRESHOLD",
    "EngineeredDetector",
    "MODEL_PATH",
    "RAW_COLUMNS",
    "REFERENCE_MODEL_PATH",
    "REFERENCE_THRESHOLD",
    "RICH_FEATURES",
    "RISKY_CATEGORIES",
    "SECOND_MODEL_FEATURES",
    "SECOND_MODEL_PATH",
    "SPEC_PATH",
    "SparkovTxn",
    "generate_batch",
    "is_fraud",
    "isoforest_is_fraud",
    "load_dataframe",
    "load_holdout_raw_rows",
    "load_raw_rows",
    "load_records",
    "load_spec",
    "raw_is_fraud",
    "reference_is_fraud",
    "sparkov_strategy",
    "retrain_with_engineered",
    "retrain_with_features",
    "verify_checksum",
]
