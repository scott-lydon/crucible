"""DummyTarget: a deterministic Shape-1 stand-in used to exercise the loop end to
end before the real fraud adapter lands (slice 2). It scores a transaction by a
fixed rule so tests are reproducible; it makes no network or LLM calls."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shared.types.core import AuditTrace
from shared.types.enums import Pillar, Shape
from shared.types.results import HealthStatus, ProducerResult


class DummyTarget:
    kind: str = "dummy"
    shape: Shape = Shape.shape1_ml

    def __init__(self, decision_threshold: float = 0.5) -> None:
        self._threshold = decision_threshold

    async def submit(self, payload: Mapping[str, Any]) -> ProducerResult:
        amount = float(payload.get("amount", 0.0))
        # Deterministic rule: large transactions look fraudulent, small ones do not.
        score = 0.95 if amount > 1000.0 else 0.05
        label = int(score >= self._threshold)
        return ProducerResult(
            output={"fraud_probability": score, "label": label},
            audit=AuditTrace(
                pillar=Pillar.targets,
                summary=f"dummy scored amount={amount} -> p={score}",
                detail={"amount": amount, "rule": "amount>1000"},
            ),
        )

    async def health(self) -> HealthStatus:
        result = await self.submit({"amount": 2000.0})
        ok = result.output["label"] == 1
        return HealthStatus(
            status="green" if ok else "red",
            detail={"target": "dummy", "roundtrip": dict(result.output)},
        )
