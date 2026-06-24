"""FraudTarget: a Shape 1 target wrapping a LightGBM fraud classifier.

The model is trained on the real Kaggle credit-card dataset (see train.py) and
loaded from a committed artifact. `submit` and `query_target` both return the
model's fraud probability for a transaction. The red agent uses `query_target`
to probe the model while searching for an evasion.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np

from modules.targets.fraud.errors import FraudModelMissingError
from shared.types import (
    AuditStep,
    AuditTrace,
    ProbeResult,
    ProbeStatus,
    SealedSpec,
    TargetOutput,
    TargetType,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ARTIFACT_PATH = _REPO_ROOT / "artifacts" / "fraud-v1.lgb"
DEFAULT_METADATA_PATH = _REPO_ROOT / "artifacts" / "fraud-v1.meta.json"


@lru_cache(maxsize=4)
def _load(artifact_path: str, metadata_path: str) -> tuple[Any, list[str], dict[str, Any]]:
    """Load the booster, its feature order, and metadata. Cached per path."""
    artifact = Path(artifact_path)
    metadata = Path(metadata_path)
    if not artifact.exists() or not metadata.exists():
        raise FraudModelMissingError(
            f"Fraud model not found at {artifact} and {metadata}. Train it with: "
            f"python scripts/fetch_fraud_dataset.py && python -m modules.targets.fraud.train"
        )
    booster = lgb.Booster(model_file=str(artifact))
    meta: dict[str, Any] = json.loads(metadata.read_text(encoding="utf-8"))
    return booster, list(meta["features"]), meta


def feature_row(attack_input: dict[str, Any], features: list[str]) -> list[float]:
    """Build the model's feature vector from a transaction dict, in train order.

    A feature absent from the transaction defaults to 0.0 (an absent signal);
    present values are coerced to float. Order matches training exactly, so the
    booster never sees transposed columns.
    """
    return [float(attack_input.get(name, 0.0)) for name in features]


@dataclass(frozen=True, slots=True)
class FraudTarget:
    """A fraud-probability model behind the Target Protocol."""

    artifact_path: Path = DEFAULT_ARTIFACT_PATH
    metadata_path: Path = DEFAULT_METADATA_PATH

    target_type: TargetType = TargetType.FRAUD

    @property
    def oracle_verified(self) -> bool:
        """A scored model: evasion is the model's own query_target miss, not the
        code oracles (Pillar 2). False routes the loop to the red search's
        score-based evasion signal for this target's success."""
        return False

    @property
    def display_name(self) -> str:
        """Name shown on the launcher's target picker."""
        return "Fraud"

    @property
    def description(self) -> str:
        """One-line tagline shown beneath the picker name."""
        return "Transaction-fraud classifier adapter (LightGBM)."

    @property
    def artifact_ref(self) -> str:
        """``fraud_adapter@<short-sha>`` derived from the committed model bytes.

        The version is the first 8 chars of the LightGBM model file's sha256,
        so the string changes whenever the model artifact does. Falls back to
        ``unknown`` when the model file is missing (the self_test reports the
        missing-model case in detail; the launcher just shows ``unknown``).
        """
        if not self.artifact_path.exists():
            return "fraud_adapter@unknown"
        digest = hashlib.sha256(self.artifact_path.read_bytes()).hexdigest()
        return f"fraud_adapter@{digest[:8]}"

    async def submit(self, spec: SealedSpec, attack_input: dict[str, Any]) -> TargetOutput:
        """Score a transaction and return its fraud probability."""
        probability = await self.query_target(attack_input)
        audit = AuditTrace(
            summary="fraud model scored a transaction",
            steps=(AuditStep(label="predict", detail={"fraud_probability": probability}),),
        )
        return TargetOutput(
            output={"fraud_probability": probability},
            score=probability,
            audit=audit,
        )

    async def query_target(self, attack_input: dict[str, Any]) -> float:
        """Return the model's fraud probability in [0, 1] for one transaction."""
        booster, features, _ = _load(str(self.artifact_path), str(self.metadata_path))
        row = np.asarray([feature_row(attack_input, features)], dtype=float)
        return float(booster.predict(row)[0])

    async def self_test(self) -> ProbeResult:
        """Report the model checksum, training time, and held-out AUC (US-8).

        Catches the missing-model case to report a red status rather than crash:
        a self-test's job is to turn a failure into a status, which is the one
        sanctioned recover-and-continue site alongside the API boundary.
        """
        try:
            _, _, meta = _load(str(self.artifact_path), str(self.metadata_path))
        except FraudModelMissingError as exc:
            return ProbeResult(status=ProbeStatus.RED, detail={"error": str(exc)})
        model_sha = hashlib.sha256(self.artifact_path.read_bytes()).hexdigest()
        return ProbeResult(
            status=ProbeStatus.GREEN,
            detail={
                "auc": meta["auc"],
                "trained_at": meta["trained_at"],
                "model_sha256": model_sha[:16],
                "model_file": self.artifact_path.name,
            },
        )
