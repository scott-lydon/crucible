from examples.targets.fraud_synth.constants import (
    AMOUNT_SCALE,
    A_HIGH,
    BATCH_FRAUD_RATE,
    DETECTOR_THRESHOLD,
    MERCHANT_RISK_HIGH,
    V_THRESH,
)
from examples.targets.fraud_synth.detector import FlawedDetector
from examples.targets.fraud_synth.generator import generate_batch
from examples.targets.fraud_synth.rule import is_fraud
from examples.targets.fraud_synth.strategy import synth_strategy
from examples.targets.fraud_synth.transaction import Transaction

__all__ = [
    "AMOUNT_SCALE",
    "A_HIGH",
    "BATCH_FRAUD_RATE",
    "DETECTOR_THRESHOLD",
    "MERCHANT_RISK_HIGH",
    "V_THRESH",
    "FlawedDetector",
    "Transaction",
    "generate_batch",
    "is_fraud",
    "synth_strategy",
]
