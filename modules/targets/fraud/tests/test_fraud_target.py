"""Unit tests for the fraud target that need no trained model or dataset."""

from __future__ import annotations

from pathlib import Path

from modules.targets.fraud import FraudTarget, feature_row
from shared.types import ProbeStatus


def test_feature_row_orders_and_defaults_missing() -> None:
    features = ["V1", "Amount"]
    assert feature_row({"V1": 1.5, "Amount": 10, "extra": 99}, features) == [1.5, 10.0]
    assert feature_row({"V1": 2.0}, features) == [2.0, 0.0]


async def test_self_test_red_when_model_missing(tmp_path: Path) -> None:
    target = FraudTarget(
        artifact_path=tmp_path / "missing.lgb",
        metadata_path=tmp_path / "missing.json",
    )
    result = await target.self_test()
    assert result.status == ProbeStatus.RED
    assert "Train it" in result.detail["error"]
