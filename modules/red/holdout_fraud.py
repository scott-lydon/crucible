"""HoldoutFraudRed: draws real transactions from the sealed held-out partition (labels
the producer never trained on) and presents them as attacks, focusing on frauds — the
hard cases that test whether the producer, and then the oracle ensemble, catch missed
fraud. The true label rides in ``attack.metadata`` for the held-out oracle only; the
producer is handed just the features. Deterministic (indexed by round), so runs replay.

This is the fraud red agent for the black-box pass; the LLM hybrid search (slice 13)
layers on top to craft harder cases."""

from __future__ import annotations

from collections.abc import Sequence

from shared.datasets.fraud import load_splits
from shared.types.core import Attack, Verdict
from shared.types.ids import AttackId, RunId, new_id
from shared.types.results import HealthStatus
from shared.types.sealed_spec import SealedSpec


class HoldoutFraudRed:
    def __init__(self, samples: Sequence[tuple[dict[str, float], int]]) -> None:
        self._samples = list(samples)

    @classmethod
    def load(cls) -> HoldoutFraudRed:
        splits = load_splits()
        fraud_idx = splits.y_holdout[splits.y_holdout == 1].index.tolist()
        samples = [
            ({k: float(v) for k, v in splits.x_holdout.loc[idx].to_dict().items()}, 1)
            for idx in fraud_idx
        ]
        return cls(samples)

    async def propose(
        self,
        spec: SealedSpec,
        run_id: RunId,
        round_index: int,
        last_verdict: Verdict | None,
        white_box: bool,
    ) -> Attack:
        features, true_label = self._samples[round_index % len(self._samples)]
        return Attack(
            attack_id=AttackId(new_id("atk")),
            run_id=run_id,
            round_index=round_index,
            tactic="holdout-fraud",
            payload=dict(features),
            rationale="Real held-out fraudulent transaction the producer never trained on.",
            seed=f"holdout-{round_index}",
            white_box=white_box,
            metadata={"true_label": true_label},
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(
            status="green",
            detail={"red": "holdout-fraud", "n_samples": len(self._samples)},
        )
