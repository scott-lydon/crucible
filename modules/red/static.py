"""StaticRedAgent: a deterministic RedAgent that cycles a fixed list of probe
inputs. It lets the loop exercise the red -> submit path before the real LLM search
lands (slice 11), and stays useful afterward as a reproducible baseline and as the
mock-mode red agent for CI (spec US-15)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from shared.types.core import Attack, Verdict
from shared.types.ids import AttackId, RunId, new_id
from shared.types.results import HealthStatus
from shared.types.sealed_spec import SealedSpec

_DEFAULT_PROBES: tuple[dict[str, Any], ...] = (
    {"amount": 1500.0},
    {"amount": 25.0},
    {"amount": 9999.0},
)


class StaticRedAgent:
    def __init__(self, probes: Sequence[dict[str, Any]] | None = None) -> None:
        self._probes = tuple(probes) if probes else _DEFAULT_PROBES

    async def propose(
        self,
        spec: SealedSpec,
        run_id: RunId,
        round_index: int,
        last_verdict: Verdict | None,
        white_box: bool,
    ) -> Attack:
        payload = self._probes[round_index % len(self._probes)]
        return Attack(
            attack_id=AttackId(new_id("atk")),
            run_id=run_id,
            round_index=round_index,
            tactic="static-probe",
            payload=dict(payload),
            rationale=f"static probe #{round_index} (white_box={white_box})",
            seed=f"static-{round_index}",
            white_box=white_box,
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(status="green", detail={"red": "static", "n_probes": len(self._probes)})
