"""FraudTarget: the Shape-1 adapter wrapping the trained LightGBM classifier. It
scores one transaction (a dict of features) and returns a fraud probability plus the
0/1 label at the model's decision threshold. No network, no LLM — a deterministic
classifier the customer owns (docs/VOCABULARY.md Shape 1)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

import lightgbm as lgb

from modules.targets.fraud.train import meta_path, model_path
from shared.types.core import AuditTrace
from shared.types.enums import Pillar, Shape
from shared.types.results import HealthStatus, ProducerResult


class FraudTarget:
    kind: str = "fraud"
    shape: Shape = Shape.shape1_ml

    def __init__(self, booster: lgb.Booster, meta: dict[str, Any]) -> None:
        self._booster = booster
        self._meta = meta
        self._features: list[str] = list(meta["feature_names"])
        self._threshold: float = float(meta["threshold"])

    @classmethod
    def load(cls, version: int = 1, tag: str = "") -> FraudTarget:
        path = model_path(version, tag)
        if not path.exists() or not meta_path(version, tag).exists():
            stem = f"fraud-{tag}-v{version}" if tag else f"fraud-v{version}"
            raise FileNotFoundError(
                f"{stem} not trained. Run: python -m modules.targets.fraud.train"
            )
        booster = lgb.Booster(model_file=str(path))
        meta = json.loads(meta_path(version, tag).read_text(encoding="utf-8"))
        return cls(booster, meta)

    @property
    def feature_names(self) -> list[str]:
        return list(self._features)

    @property
    def feature_importances(self) -> dict[str, float]:
        """Per-feature importance from the trained booster — the red agent reasons over
        these to decide which features to attack."""
        raw = cast("Any", self._booster.feature_importance(importance_type="gain"))
        return {name: float(v) for name, v in zip(self._features, raw, strict=False)}

    def _vectorize(self, payload: Mapping[str, Any]) -> list[float]:
        return [float(payload.get(name, 0.0)) for name in self._features]

    def predict_sync(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Synchronous score, for oracles that re-query the producer (metamorphic,
        property-fuzz). Deterministic."""
        proba = cast("Any", self._booster.predict([self._vectorize(payload)]))
        score = float(proba[0])
        return {"fraud_probability": score, "label": int(score >= self._threshold)}

    def raw_margin(self, payload: Mapping[str, Any]) -> float:
        """The unsquashed log-odds margin (before the sigmoid). Smooth even where the
        probability is saturated at 0/1 — the red optimizer follows this to craft
        adversarial evasions."""
        margin = cast("Any", self._booster.predict([self._vectorize(payload)], raw_score=True))
        return float(margin[0])

    async def submit(self, payload: Mapping[str, Any]) -> ProducerResult:
        out = self.predict_sync(payload)
        score = out["fraud_probability"]
        label = out["label"]
        return ProducerResult(
            output={"fraud_probability": score, "label": label},
            audit=AuditTrace(
                pillar=Pillar.targets,
                summary=f"fraud LightGBM scored p={score:.4f} -> label={label}",
                detail={"threshold": self._threshold, "n_features": len(self._features)},
            ),
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(
            status="green",
            detail={
                "target": "fraud",
                "version": self._meta.get("version"),
                "model_sha256": self._meta.get("model_sha256"),
                "trained_at": self._meta.get("trained_at"),
                "auc_eval": self._meta.get("auc_eval"),
            },
        )
