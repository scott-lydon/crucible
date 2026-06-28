"""Blue proposer (PR3 port C1).

The first step of the fraud hardening loop: from the strategy catalog's undetected-hack
attacks, propose the adversarial feature rows the patch will be retrained on. It is the
"what should change" step, kept separate from the retrain ("how") and the held-out
validation ("did it generalize") so each is independently auditable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from shared.types.core import Attack


@dataclass(frozen=True, slots=True)
class Proposal:
    """The adversarial samples to retrain on, and the ids they came from."""

    samples: tuple[Mapping[str, float], ...]
    source_attack_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BlueProposer:
    """Selects the adversarial feature rows for the retrain from the catalog slice."""

    def propose(self, catalog_slice: Sequence[Attack]) -> Proposal:
        samples = tuple(
            {k: float(v) for k, v in a.payload.items()} for a in catalog_slice
        )
        ids = tuple(str(a.attack_id) for a in catalog_slice)
        return Proposal(samples=samples, source_attack_ids=ids)

    @staticmethod
    def as_rows(proposal: Proposal) -> list[dict[str, Any]]:
        return [dict(s) for s in proposal.samples]
