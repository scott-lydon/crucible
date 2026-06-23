"""Victim/fraud-rule parameters for the fraud_synth demo target.

These belong to the demo VICTIM (its data generator, ground-truth rule, and
the detector's own decision threshold) — NOT to the Crucible harness.
"""

AMOUNT_SCALE = 1000.0
V_THRESH = 5
A_HIGH = 800.0
MERCHANT_RISK_HIGH = 0.7
DETECTOR_THRESHOLD = 0.5
BATCH_FRAUD_RATE = 0.2
