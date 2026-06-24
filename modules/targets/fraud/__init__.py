"""Fraud target (Shape 1): a LightGBM classifier on real Kaggle data."""

from __future__ import annotations

from .fraud_target import (
    DEFAULT_ARTIFACT_PATH,
    DEFAULT_METADATA_PATH,
    FraudTarget,
    feature_row,
)

__all__ = [
    "DEFAULT_ARTIFACT_PATH",
    "DEFAULT_METADATA_PATH",
    "FraudTarget",
    "feature_row",
]
