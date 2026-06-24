"""Unit tests for the fraud target that need no trained model or dataset."""

from __future__ import annotations

from pathlib import Path

from modules.targets.fraud import FraudTarget, feature_row
from shared.types import ProbeStatus


def test_feature_row_orders_and_defaults_missing() -> None:
    features = ["V1", "Amount"]
    assert feature_row({"V1": 1.5, "Amount": 10, "extra": 99}, features) == [1.5, 10.0]
    assert feature_row({"V1": 2.0}, features) == [2.0, 0.0]


def test_feature_row_treats_null_and_non_numeric_as_absent() -> None:
    # A real red-search proposal can emit an explicit null or a string for a
    # feature; both are absent signals, not a crash (regression: the e2e run
    # died on `{"V5": null}` because get(name, 0.0) returns None for a present
    # null key and float(None) raises).
    features = ["V1", "V2", "V3", "Amount"]
    row = feature_row({"V1": None, "V2": "high", "V3": [1, 2], "Amount": 5}, features)
    assert row == [0.0, 0.0, 0.0, 5.0]


async def test_self_test_red_when_model_missing(tmp_path: Path) -> None:
    target = FraudTarget(
        artifact_path=tmp_path / "missing.lgb",
        metadata_path=tmp_path / "missing.json",
    )
    result = await target.self_test()
    assert result.status == ProbeStatus.RED
    assert "Train it" in result.detail["error"]
