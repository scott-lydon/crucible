"""Verdict aggregator. We report HOW MANY of the panel's independent oracles flagged an
output ("X of N flagged") — a plain count, each oracle one vote, no weighting. ``tally`` is
that fired count and ``threshold`` is the CORROBORATION bar (2): a verdict is "caught" only
when >= 2 independent oracles agree, which is what the silent-failure and white-box-recall
metrics need (one oracle alone, including the ground-truth held-out, can have a blind spot).
The UI shows the full count and colours by strength (0 clean, 1 flagged, >=2 corroborated);
the co-evolution loop improves on ANY firing, separately from this bar.

Deterministic: given the same producer output and the same (deterministic) oracle
votes, the verdict replays byte-for-byte (spec US-5)."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from orchestrator.interfaces import Oracle
from shared.types.core import Attack, AuditTrace, OracleVote, Verdict
from shared.types.enums import Pillar, VerdictOutcome
from shared.types.ids import RunId, VerdictId, new_id
from shared.types.sealed_spec import SealedSpec

# Corroboration bar as a COUNT (was a weighted 2.0): >= this many independent oracles must
# flag an output for it to count as "caught" (corroborated). Drives silent/recall, not the UI.
PASS_THRESHOLD = 2


def aggregate(
    run_id: RunId,
    attack: Attack,
    output: Mapping[str, Any],
    votes: Sequence[OracleVote],
    *,
    threshold: float = PASS_THRESHOLD,
) -> Verdict:
    fired_oracles = [str(v.oracle) for v in votes if v.fired]
    fired_count = len(fired_oracles)
    total = len(votes)
    # "caught" == CORROBORATED: >= threshold (2) independent oracles flagged it. The UI shows
    # the full "fired_count of total" and colours by strength; this binary only drives the
    # corroboration-dependent metrics (silent failures, white-box recall).
    outcome = VerdictOutcome.caught if fired_count >= threshold else VerdictOutcome.clean
    audit = AuditTrace(
        pillar=Pillar.oracles,
        summary=(
            f"{fired_count} of {total} oracles flagged"
            + (" (corroborated)" if outcome is VerdictOutcome.caught else "")
            + f"; fired={fired_oracles}"
        ),
        detail={"votes": [v.as_dict() for v in votes], "fired": fired_oracles,
                "fired_count": fired_count, "total": total},
    )
    return Verdict(
        verdict_id=VerdictId(new_id("vdt")),
        run_id=run_id,
        attack_id=attack.attack_id,
        producer_output=dict(output),
        votes=tuple(votes),
        tally=float(fired_count),
        threshold=float(threshold),
        outcome=outcome,
        audit=audit,
        seed=attack.seed,
        dollars=sum(v.dollars for v in votes),
    )


async def run_verdict(
    oracles: Sequence[Oracle],
    spec: SealedSpec,
    attack: Attack,
    output: Mapping[str, Any],
) -> Verdict:
    """Collect every oracle's vote on one producer output, then aggregate. Oracles are
    polled independently — none sees another's vote (non-colluding ensemble). Matches
    the VerifyFn port so wiring can inject it into the loop."""
    # Oracles are independent (none sees another's vote), so run them CONCURRENTLY; gather
    # preserves order, so the verdict still replays byte-for-byte (spec US-5).
    votes = list(await asyncio.gather(
        *(oracle.vote(spec, attack, output) for oracle in oracles)))
    return aggregate(attack.run_id, attack, output, votes)
