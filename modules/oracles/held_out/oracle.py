"""FraudHeldOutOracle: the ground-truth oracle. For the fraud target the held-out
"fresh tests" are the sealed held-out data partition (real labels the producer never
trained on — deviation from Opus-generated tests, tracked in bead cr-dev; more honest
than synthetic transactions). The true label rides in ``attack.metadata`` (which the
producer never sees); the oracle fires when the producer mislabels a known fraud.

This is the authoritative signal: when it fires, the producer is wrong by ground
truth. It still carries one vote — the ensemble must confirm with a second mechanism
to "catch" (plan.md section 3). One vote (1.0), token-free."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shared.types.core import Attack, OracleVote
from shared.types.enums import OracleKind
from shared.types.results import HealthStatus
from shared.types.sealed_spec import SealedSpec


class FraudHeldOutOracle:
    kind: OracleKind = OracleKind.held_out
    weight: float = 1.0

    async def vote(
        self, spec: SealedSpec, attack: Attack, output: Mapping[str, Any]
    ) -> OracleVote:
        obligation = spec.obligation_text("label_match")
        raw_true = attack.metadata.get("true_label")
        producer_label = int(output.get("label", 0))

        if raw_true is None:
            return OracleVote(
                oracle=self.kind, fired=False, weight=self.weight, obligation=obligation,
                observation="no held-out ground-truth label for this input",
                reason="This input is not a held-out labelled sample; the held-out oracle "
                       "abstains.",
                seed=attack.seed,
            )

        true_label = int(raw_true)
        fired = true_label == 1 and producer_label == 0
        if fired:
            reason = (
                "Held-out ground truth: this transaction is fraudulent (label=1), but the "
                "producer scored it legitimate (label=0). The producer missed a known fraud."
            )
        elif true_label == 1:
            reason = "Held-out ground truth: fraud, and the producer caught it (label=1)."
        else:
            reason = "Held-out ground truth: legitimate, and the producer agreed (label=0)."
        return OracleVote(
            oracle=self.kind, fired=fired, weight=self.weight, obligation=obligation,
            observation=f"true_label={true_label} producer_label={producer_label}",
            reason=reason, seed=attack.seed,
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(
            status="green", detail={"oracle": "held_out", "source": "data_partition"}
        )
