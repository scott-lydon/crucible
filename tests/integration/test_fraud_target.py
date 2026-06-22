"""Slice-2 done criteria: the fraud LightGBM trains on real data with AUC >= 0.85,
discriminates fraud from legit on the held-out partition, and its /health leaf is
green with the model checksum."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from modules.targets.fraud.data import load_splits
from modules.targets.fraud.target import FraudTarget
from modules.targets.fraud.train import ensure_model


def test_fraud_model_trained_on_real_data_auc() -> None:
    meta = ensure_model(1)
    assert meta["auc_eval"] >= 0.85, meta
    assert meta["n_train"] > 100_000           # real dataset, not a stub
    assert len(meta["feature_names"]) >= 28


def test_fraud_target_discriminates_on_holdout() -> None:
    splits = load_splits()
    target = FraudTarget.load(1)

    fraud_idx = splits.y_holdout[splits.y_holdout == 1].index[:40]
    legit_idx = splits.y_holdout[splits.y_holdout == 0].index[:40]

    async def _scores(indices: object) -> list[float]:
        out: list[float] = []
        for idx in indices:  # type: ignore[attr-defined]
            row = splits.x_holdout.loc[idx].to_dict()
            result = await target.submit(row)
            out.append(float(result.output["fraud_probability"]))
        return out

    fraud_scores = asyncio.run(_scores(fraud_idx))
    legit_scores = asyncio.run(_scores(legit_idx))

    mean_fraud = sum(fraud_scores) / len(fraud_scores)
    mean_legit = sum(legit_scores) / len(legit_scores)
    caught = sum(1 for s in fraud_scores if s >= 0.5) / len(fraud_scores)

    assert mean_fraud > mean_legit, (mean_fraud, mean_legit)
    assert caught >= 0.7, caught     # recall on held-out frauds the model never trained on


def test_fraud_health_green(client: TestClient) -> None:
    health = client.get("/health").json()
    leaf = health["targets/fraud"]
    assert leaf["status"] == "green", leaf
    assert leaf["detail"]["model_sha256"]
    assert leaf["detail"]["auc_eval"] >= 0.85
