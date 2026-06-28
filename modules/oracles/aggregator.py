"""Verdict aggregator. Vote-weighted: each of the four independent oracles carries
one vote, the LLM judge half a vote; the ensemble "catches" producer wrongness when
the fired weight reaches the threshold (2.0). The half-vote judge can therefore never
decide a verdict alone (spec US-4), and a single oracle (weight 1.0) cannot either —
two independent mechanisms must agree (plan.md section 3).

Deterministic: given the same producer output and the same (deterministic) oracle
votes, the verdict replays byte-for-byte (spec US-5).

Replay determinism (PR3 port A3). ``vote_as_json`` / ``vote_from_json`` /
``votes_from_json`` are the one round-tripping serialization that the persisted
verdict and the replay path both use (single point of truth), so a stored verdict
and its replay cannot drift. ``vote_as_json`` is the canonical serializer
(``OracleVote.as_dict``); ``vote_from_json`` is its exact inverse, parsing at the
boundary so a malformed row surfaces as a typed error from the value object rather
than a silent coercion downstream. For any vote ``v``::

    vote_as_json(vote_from_json(vote_as_json(v))) == vote_as_json(v)

holds byte-for-byte, which is what the Audit Row Replayer compares."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from orchestrator.interfaces import Oracle
from shared.types.core import Attack, AuditTrace, OracleVote, Verdict
from shared.types.enums import OracleKind, Pillar, VerdictOutcome
from shared.types.ids import RunId, VerdictId, new_id
from shared.types.sealed_spec import SealedSpec

PASS_THRESHOLD = 2.0


def vote_as_json(vote: OracleVote) -> dict[str, Any]:
    """Serialize one vote for the ``verdicts`` audit JSONB and for replay comparison.

    The canonical serializer: it delegates to ``OracleVote.as_dict`` so there is exactly
    one shape on the wire (no second, drifting copy)."""
    return vote.as_dict()


def vote_from_json(data: Mapping[str, Any]) -> OracleVote:
    """Rebuild one vote from its stored form, the exact inverse of ``vote_as_json``.

    Parses at the boundary (the trusted JSON we wrote): each field is coerced to its
    declared type, so a malformed row raises here rather than corrupting a replayed
    verdict silently."""
    return OracleVote(
        oracle=OracleKind(str(data["oracle"])),
        fired=bool(data["fired"]),
        weight=float(data["weight"]),
        obligation=str(data["obligation"]),
        observation=str(data["observation"]),
        reason=str(data["reason"]),
        seed=str(data["seed"]),
        dollars=float(data.get("dollars", 0.0)),
        available=bool(data.get("available", True)),
    )


def votes_from_json(rows: Sequence[Mapping[str, Any]]) -> tuple[OracleVote, ...]:
    """Rebuild the ordered vote tuple from the stored audit ``votes`` list, preserving
    order so the replayed verdict's tally arithmetic matches the original."""
    return tuple(vote_from_json(row) for row in rows)


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
    votes = [await oracle.vote(spec, attack, output) for oracle in oracles]
    return aggregate(attack.run_id, attack, output, votes)
