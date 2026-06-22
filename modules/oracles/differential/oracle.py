"""FraudDifferentialOracle: cross-checks the LightGBM producer against an independent
IsolationForest. It fires when the differential model's anomaly score crosses the
calibrated threshold (fraud-like) but the producer labelled the transaction
legitimate — evidence the producer missed fraud (docs/VOCABULARY.md "producer
wrongness"). One vote (weight 1.0). Token-free."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import numpy as np
from sklearn.ensemble import IsolationForest

from modules.oracles.differential.model import load_isoforest
from shared.types.core import Attack, OracleVote
from shared.types.enums import OracleKind
from shared.types.results import HealthStatus
from shared.types.sealed_spec import SealedSpec


def _obligation_text(spec: SealedSpec) -> str:
    for obligation in spec.obligations:
        if obligation.check_kind == "label_match":
            return obligation.description
    return spec.obligations[0].description if spec.obligations else "(no obligation declared)"


class FraudDifferentialOracle:
    kind: OracleKind = OracleKind.differential
    weight: float = 1.0

    def __init__(self, model: IsolationForest, features: list[str], threshold: float) -> None:
        self._model = model
        self._features = features
        self._threshold = threshold

    @classmethod
    def load(cls, version: int = 1) -> FraudDifferentialOracle:
        model, features, threshold = load_isoforest(version)
        return cls(model, features, threshold)

    def _anomaly_score(self, payload: Mapping[str, Any]) -> float:
        vec = np.asarray([[float(payload.get(name, 0.0)) for name in self._features]])
        return -float(cast("Any", self._model.decision_function(vec))[0])

    async def vote(
        self, spec: SealedSpec, attack: Attack, output: Mapping[str, Any]
    ) -> OracleVote:
        score = self._anomaly_score(attack.payload)
        diff_label = 1 if score >= self._threshold else 0
        producer_label = int(output.get("label", 0))
        fired = diff_label == 1 and producer_label == 0
        if fired:
            reason = (
                f"IsolationForest anomaly score {score:.4f} exceeds the calibrated "
                f"threshold {self._threshold:.4f} (fraud-like), but the producer labelled "
                f"the transaction legitimate. A different model family asserts missed fraud."
            )
        else:
            reason = (
                f"IsolationForest anomaly score {score:.4f} vs threshold "
                f"{self._threshold:.4f}; producer label={producer_label}. No missed-fraud "
                f"disagreement."
            )
        return OracleVote(
            oracle=self.kind,
            fired=fired,
            weight=self.weight,
            obligation=_obligation_text(spec),
            observation=(
                f"anomaly_score={score:.4f} threshold={self._threshold:.4f} "
                f"diff_label={diff_label} producer_label={producer_label}"
            ),
            reason=reason,
            seed=attack.seed,
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(
            status="green",
            detail={
                "oracle": "differential",
                "family": "IsolationForest",
                "anomaly_threshold": self._threshold,
                "n_features": len(self._features),
            },
        )
