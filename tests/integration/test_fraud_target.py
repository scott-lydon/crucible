"""Slice 2 done-criterion: a real Kaggle-trained fraud model, AUC >= 0.85.

Runs against the committed `artifacts/fraud-v1.lgb` (trained on the real
dataset), so it needs no 150 MB download. Skips only if the artifact or
lightgbm is absent.
"""

from __future__ import annotations

import importlib.util

import pytest
from httpx import AsyncClient

from modules.targets.fraud import DEFAULT_ARTIFACT_PATH, DEFAULT_METADATA_PATH, FraudTarget
from shared.types import ProbeStatus, SealedSpec

_READY = (
    DEFAULT_ARTIFACT_PATH.exists()
    and DEFAULT_METADATA_PATH.exists()
    and importlib.util.find_spec("lightgbm") is not None
)

pytestmark = pytest.mark.skipif(not _READY, reason="trained fraud model + lightgbm required")

_SAMPLE_TXN = {"V1": -1.36, "V2": -0.07, "V3": 2.54, "V14": -0.31, "Amount": 149.62}


def _spec() -> SealedSpec:
    return SealedSpec.from_payload(
        {
            "title": "fraud",
            "obligations": [{"id": "o1", "description": "flag fraudulent transactions"}],
        }
    )


async def test_self_test_green_and_auc_meets_bar() -> None:
    result = await FraudTarget().self_test()
    assert result.status == ProbeStatus.GREEN
    assert result.detail["auc"] >= 0.85


async def test_query_target_returns_probability() -> None:
    probability = await FraudTarget().query_target(_SAMPLE_TXN)
    assert 0.0 <= probability <= 1.0


async def test_submit_returns_fraud_probability() -> None:
    output = await FraudTarget().submit(_spec(), _SAMPLE_TXN)
    assert output.score is not None
    assert 0.0 <= output.score <= 1.0
    assert "fraud_probability" in output.output


async def test_fraud_health_route_returns_200_green(client: AsyncClient) -> None:
    resp = await client.get("/health/targets/fraud")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "green"
