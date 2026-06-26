"""FraudMetamorphicOracle: checks metamorphic relations — semantically-neutral input
transforms whose label the producer must preserve (plan.md section 3). Three rules
synthesized from the spec invariants (mock-first; the Sonnet rule-synthesis hook is
the production path, bead cr-dev):

  R1  tiny uniform jitter (±2%) preserves the label
  R2  scaling Amount by +1% preserves the label
  R3  scaling all features by -1% preserves the label

A flip means the producer's decision is unstable on a semantically-equivalent input —
evidence the verdict on this input cannot be trusted. One vote (1.0), token-free.
Deterministic (seed derived from the attack), so it replays."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np

from shared.types.core import Attack, OracleVote
from shared.types.enums import OracleKind
from shared.types.results import HealthStatus
from shared.types.sealed_spec import SealedSpec

PredictFn = Callable[[Mapping[str, Any]], dict[str, Any]]


class FraudMetamorphicOracle:
    kind: OracleKind = OracleKind.metamorphic
    weight: float = 1.0

    def __init__(
        self, predict: PredictFn, feature_names: list[str], *, epsilon: float = 0.02
    ) -> None:
        self._predict = predict
        self._features = feature_names
        self._epsilon = epsilon

    def _label(self, payload: Mapping[str, Any]) -> int:
        return int(self._predict(payload)["label"])

    def _rules(self, payload: Mapping[str, Any], seed: str) -> list[tuple[str, dict[str, Any]]]:
        base = {k: float(v) for k, v in payload.items()}
        seed_int = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
        rng = np.random.RandomState(seed_int)
        jitter = {
            k: v * (1.0 + rng.uniform(-self._epsilon, self._epsilon)) for k, v in base.items()
        }
        amount_up = {**base, "Amount": base.get("Amount", 0.0) * 1.01}
        scaled_down = {k: v * 0.99 for k, v in base.items()}
        return [
            ("R1 uniform-jitter-preserves-label", jitter),
            ("R2 amount-scale-preserves-label", amount_up),
            ("R3 global-scale-preserves-label", scaled_down),
        ]

    async def vote(
        self, spec: SealedSpec, attack: Attack, output: Mapping[str, Any]
    ) -> OracleVote:
        base_label = int(output.get("label", self._label(attack.payload)))
        violated: list[str] = []
        for name, transformed in self._rules(attack.payload, attack.seed):
            if self._label(transformed) != base_label:
                violated.append(name)
        fired = len(violated) > 0
        if fired:
            reason = (
                f"Metamorphic relation(s) violated: {violated}. The producer's label "
                f"flipped under semantically-neutral transform(s); the decision on this "
                f"input is unstable and cannot be trusted."
            )
        else:
            reason = ("All three metamorphic relations held: the label is stable under "
                      "neutral transforms.")
        return OracleVote(
            oracle=self.kind, fired=fired, weight=self.weight,
            obligation=spec.obligation_text("label_match"),
            observation=f"rules_checked=3 violated={violated} base_label={base_label}",
            reason=reason, seed=attack.seed,
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(status="green", detail={"oracle": "metamorphic", "n_rules": 3})
