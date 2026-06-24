from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent
_ARTIFACT = _REPO_ROOT / "artifacts" / "fraud-v2.lgb"
_METADATA = _REPO_ROOT / "artifacts" / "fraud-v2.meta.json"

_TRANSACTION = {
    "V2": 0.0,
    "V4": 0.0,
    "V5": 0.0,
    "V6": 0.0,
    "V7": 0.0,
    "V8": 0.0,
    "V9": 0.0,
    "V11": 0.0,
    "V12": 0.0,
    "V13": 0.0,
    "V15": 0.0,
    "V16": 0.0,
    "V18": 0.0,
    "V19": 0.0,
    "V20": 0.0,
    "V21": 0.0,
    "V22": 0.0,
    "V23": 0.0,
    "V24": 0.0,
    "V25": 0.0,
    "V26": 0.0,
    "V27": 0.0,
    "V28": 0.0,
    "Time": 126542.20369843947,
    "Amount": 8286.7945846026,
    "V1": -0.825509818194417,
    "V3": 1.022559074852385,
    "V10": -3.350390182201013,
    "V14": -0.8922986853179782,
    "V17": 0.6372512339958369,
}


def predict(transaction: dict) -> float:
    meta = json.loads(_METADATA.read_text(encoding="utf-8"))
    features: list[str] = meta["features"]
    booster = lgb.Booster(model_file=str(_ARTIFACT))
    row = np.asarray(
        [[float(transaction.get(f, 0.0)) for f in features]],
        dtype=float,
    )
    return float(booster.predict(row)[0])


if __name__ == "__main__":
    prob = predict(_TRANSACTION)
    print(json.dumps({"fraud_probability": prob}))
