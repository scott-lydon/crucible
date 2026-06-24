"""Verdict aggregator unit tests: the pure vote-tally and audit logic.

No I/O: the aggregator is a pure function of its votes and ids, so these run
fast in CI with no database, no LLM, and no sandbox.
"""

from __future__ import annotations

import json

from modules.oracles.aggregator import (
    VerdictAggregator,
    vote_as_json,
    vote_from_json,
    votes_from_json,
)
from shared.types import AttackId, OracleVote, RunId, Verdict, VerdictDecision, VerdictId


def _vote(name: str, decision: VerdictDecision, weight: float = 1.0) -> OracleVote:
    return OracleVote(
        oracle_name=name,
        decision=decision,
        weight=weight,
        reason=f"{name} voted {decision.value}",
        obligation_id="o1",
    )


def _aggregate(
    votes: tuple[OracleVote, ...], *, threshold: float = 2.0
) -> Verdict:
    return VerdictAggregator(pass_threshold=threshold).aggregate(
        votes,
        run_id=RunId("run-1"),
        attack_id=AttackId("atk-1"),
        verdict_id=VerdictId("vd-1"),
    )


def test_passes_when_pass_weight_reaches_threshold() -> None:
    votes = (
        _vote("held_out", VerdictDecision.PASS),
        _vote("metamorphic", VerdictDecision.PASS),
        _vote("differential", VerdictDecision.FAIL),
    )
    verdict = _aggregate(votes)
    assert verdict.tally == 2.0
    assert verdict.passed is True


def test_caught_when_pass_weight_below_threshold() -> None:
    votes = (
        _vote("held_out", VerdictDecision.PASS),
        _vote("metamorphic", VerdictDecision.FAIL),
        _vote("differential", VerdictDecision.FAIL),
    )
    verdict = _aggregate(votes)
    assert verdict.tally == 1.0
    assert verdict.passed is False


def test_threshold_is_inclusive_at_exactly_two() -> None:
    votes = (
        _vote("held_out", VerdictDecision.PASS),
        _vote("metamorphic", VerdictDecision.PASS),
    )
    verdict = _aggregate(votes)
    assert verdict.tally == 2.0
    assert verdict.passed is True


def test_judge_half_weight_alone_cannot_pass() -> None:
    # The judge voting pass on its own is 0.5, far below 2.0: it can never
    # carry a verdict by itself (US-4).
    verdict = _aggregate((_vote("llm_judge", VerdictDecision.PASS, weight=0.5),))
    assert verdict.tally == 0.5
    assert verdict.passed is False


def test_full_ensemble_pass_weight_includes_the_half_weight_judge() -> None:
    votes = (
        _vote("held_out", VerdictDecision.PASS),
        _vote("metamorphic", VerdictDecision.PASS),
        _vote("differential", VerdictDecision.PASS),
        _vote("property_fuzz", VerdictDecision.PASS),
        _vote("llm_judge", VerdictDecision.PASS, weight=0.5),
    )
    verdict = _aggregate(votes)
    assert verdict.tally == 4.5
    assert verdict.passed is True


def test_unavailable_votes_contribute_nothing() -> None:
    votes = (
        _vote("held_out", VerdictDecision.PASS),
        _vote("metamorphic", VerdictDecision.UNAVAILABLE),
        _vote("differential", VerdictDecision.UNAVAILABLE),
    )
    verdict = _aggregate(votes)
    assert verdict.tally == 1.0
    assert verdict.passed is False


def test_custom_threshold_raises_the_bar() -> None:
    votes = (
        _vote("held_out", VerdictDecision.PASS),
        _vote("metamorphic", VerdictDecision.PASS),
    )
    verdict = _aggregate(votes, threshold=3.0)
    assert verdict.tally == 2.0
    assert verdict.passed is False


def test_audit_trace_names_every_vote_then_the_tally() -> None:
    votes = (
        _vote("held_out", VerdictDecision.PASS),
        _vote("llm_judge", VerdictDecision.FAIL, weight=0.5),
    )
    verdict = _aggregate(votes)
    steps = verdict.audit.steps
    assert len(steps) == len(votes) + 1
    assert [s.label for s in steps[:-1]] == ["vote:held_out", "vote:llm_judge"]
    tally_step = steps[-1]
    assert tally_step.label == "tally"
    assert tally_step.detail["pass_weight"] == 1.0
    assert tally_step.detail["pass_threshold"] == 2.0
    assert tally_step.detail["passed"] is False
    # The held-out PASS counted; the judge FAIL did not.
    assert steps[0].detail["counted_toward_pass"] is True
    assert steps[1].detail["counted_toward_pass"] is False


def test_verdict_carries_its_ids() -> None:
    verdict = _aggregate((_vote("held_out", VerdictDecision.PASS),))
    assert verdict.verdict_id.value == "vd-1"
    assert verdict.run_id.value == "run-1"
    assert verdict.attack_id is not None
    assert verdict.attack_id.value == "atk-1"


def test_vote_json_round_trips_including_null_obligation() -> None:
    vote = OracleVote(
        oracle_name="differential",
        decision=VerdictDecision.UNAVAILABLE,
        weight=1.0,
        reason="inconclusive",
        obligation_id=None,
    )
    restored = vote_from_json(vote_as_json(vote))
    assert restored == vote


def test_votes_from_json_preserves_order() -> None:
    votes = (
        _vote("held_out", VerdictDecision.PASS),
        _vote("metamorphic", VerdictDecision.FAIL),
        _vote("llm_judge", VerdictDecision.PASS, weight=0.5),
    )
    agg = VerdictAggregator()
    restored = votes_from_json(agg.votes_as_json(votes))
    assert restored == votes


def test_reaggregation_from_persisted_votes_is_byte_equal() -> None:
    # The replay-determinism guarantee at the pure-function level: serialize,
    # reconstruct, re-aggregate, and the verdict content is byte-identical.
    agg = VerdictAggregator()
    votes = (
        _vote("held_out", VerdictDecision.PASS),
        _vote("metamorphic", VerdictDecision.PASS),
        _vote("llm_judge", VerdictDecision.FAIL, weight=0.5),
    )
    first = agg.aggregate(
        votes, run_id=RunId("r"), attack_id=AttackId("a"), verdict_id=VerdictId("v")
    )
    stored = agg.votes_as_json(first.votes)

    replayed = agg.aggregate(
        votes_from_json(stored),
        run_id=RunId("r"),
        attack_id=AttackId("a"),
        verdict_id=VerdictId("v"),
    )

    def content(verdict: Verdict) -> str:
        return json.dumps(
            {
                "passed": verdict.passed,
                "tally": verdict.tally,
                "votes": agg.votes_as_json(verdict.votes),
                "audit_trace": verdict.audit.as_json(),
            },
            sort_keys=True,
        )

    assert content(first) == content(replayed)
