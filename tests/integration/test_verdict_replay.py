"""Slice 10 done-criterion: a persisted verdict replays byte-for-byte.

A verdict is aggregated from a set of oracle votes and persisted to the
verdicts table. Reading it back, reconstructing the votes, and re-aggregating
under the same verdict id reproduces byte-identical content (votes, tally,
passed, audit trace). The aggregator is pure, so the replay cannot drift from
the stored row. Real Postgres, no mocks.
"""

from __future__ import annotations

import json
from decimal import Decimal

from modules.oracles.aggregator import VerdictAggregator, votes_from_json
from shared.persistence import get_sessionmaker
from shared.persistence.models import Attack, Run
from shared.persistence.models import Verdict as VerdictRow
from shared.types import AttackId, OracleVote, RunId, Verdict, VerdictDecision, VerdictId


def _votes() -> tuple[OracleVote, ...]:
    return (
        OracleVote("held_out", VerdictDecision.PASS, 1.0, "all held-out tests passed", "o1"),
        OracleVote("metamorphic", VerdictDecision.FAIL, 1.0, "relation r2 violated", "o1"),
        OracleVote("differential", VerdictDecision.PASS, 1.0, "families agree", "o1"),
        OracleVote("property_fuzz", VerdictDecision.UNAVAILABLE, 1.0, "harness errored", "o1"),
        OracleVote("llm_judge", VerdictDecision.PASS, 0.5, "looks correct to the judge", "o1"),
    )


def _content(agg: VerdictAggregator, verdict: Verdict) -> str:
    """The canonical JSON content compared across the persist-then-replay boundary."""
    return json.dumps(
        {
            "passed": verdict.passed,
            "tally": verdict.tally,
            "votes": agg.votes_as_json(verdict.votes),
            "audit_trace": verdict.audit.as_json(),
        },
        sort_keys=True,
    )


async def test_persisted_verdict_replays_byte_equal(migrated_database: str) -> None:
    agg = VerdictAggregator()
    run_id = RunId.new()
    attack_id = AttackId.new()
    verdict_id = VerdictId.new()

    verdict = agg.aggregate(
        _votes(), run_id=run_id, attack_id=attack_id, verdict_id=verdict_id
    )

    async with get_sessionmaker()() as session:
        # Insert in foreign-key order (run, then attack, then verdict), flushing
        # each so the parent row exists before the child references it.
        session.add(
            Run(
                id=run_id.value,
                target_type="code_agent",
                artifact_ref="replay-fixture",
                spec_title="add",
                spec_json={"title": "add", "obligations": [{"id": "o1", "description": "adds"}]},
                budget_max_attempts=1,
                budget_max_dollars=Decimal("1"),
                seed="seed-1",
            )
        )
        await session.flush()
        session.add(
            Attack(
                id=attack_id.value,
                run_id=run_id.value,
                tactic="seed-probe",
                payload={"probe": "seed"},
                succeeded=False,
                seed="seed-1",
                audit_trace={"summary": "probe", "steps": []},
            )
        )
        await session.flush()
        session.add(
            VerdictRow(
                id=verdict_id.value,
                run_id=run_id.value,
                attack_id=attack_id.value,
                passed=verdict.passed,
                tally=verdict.tally,
                votes=agg.votes_as_json(verdict.votes),
                seed="seed-1",
                audit_trace=verdict.audit.as_json(),
                parent_action_id=attack_id.value,
            )
        )
        await session.commit()

    async with get_sessionmaker()() as session:
        stored = await session.get(VerdictRow, verdict_id.value)
        assert stored is not None

        replayed = agg.aggregate(
            votes_from_json(stored.votes),
            run_id=RunId(stored.run_id),
            attack_id=AttackId(stored.attack_id) if stored.attack_id else None,
            verdict_id=VerdictId(stored.id),
        )

        stored_content = json.dumps(
            {
                "passed": stored.passed,
                "tally": stored.tally,
                "votes": stored.votes,
                "audit_trace": stored.audit_trace,
            },
            sort_keys=True,
        )
        assert _content(agg, replayed) == stored_content
        # The recorded outcome is the real tally: 2.5 pass-weight clears 2.0.
        assert stored.tally == 2.5
        assert stored.passed is True
