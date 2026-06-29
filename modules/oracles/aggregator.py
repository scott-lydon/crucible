"""Verdict aggregator. Vote-weighted: each of the four independent oracles carries
one vote, the LLM judge half a vote; the ensemble "catches" producer wrongness when
the fired weight reaches the threshold (2.0). The half-vote judge can therefore never
decide a verdict alone (spec US-4), and a single oracle (weight 1.0) cannot either —
two independent mechanisms must agree (plan.md section 3).

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

PASS_THRESHOLD = 2.0


def aggregate(
    run_id: RunId,
    attack: Attack,
    output: Mapping[str, Any],
    votes: Sequence[OracleVote],
    *,
    threshold: float = PASS_THRESHOLD,
) -> Verdict:
    tally = sum(v.weight for v in votes if v.fired)
    outcome = VerdictOutcome.caught if tally >= threshold else VerdictOutcome.clean
    fired_oracles = [str(v.oracle) for v in votes if v.fired]
    audit = AuditTrace(
        pillar=Pillar.oracles,
        summary=(
            f"{outcome}: fired weight {tally:.1f} / threshold {threshold:.1f} "
            f"from {len(votes)} oracle(s); fired={fired_oracles}"
        ),
        detail={"votes": [v.as_dict() for v in votes], "fired": fired_oracles},
    )
    return Verdict(
        verdict_id=VerdictId(new_id("vdt")),
        run_id=run_id,
        attack_id=attack.attack_id,
        producer_output=dict(output),
        votes=tuple(votes),
        tally=tally,
        threshold=threshold,
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
