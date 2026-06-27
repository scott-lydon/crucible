"""Verification finding #1 (Gustavo / Measure lane): the headline white-box catch
rate is structurally blind to attacks that evade the ground-truth oracle.

``modules/measure/metrics.py`` defines "the producer was wrong" as "the held-out
oracle fired" (``_held_out_fired``). The held-out oracle is also a 1.0-weight voter in
the same ensemble whose ``caught`` outcome it grades. So a white-box attacker who
crafts an evasion the held-out oracle MISSES contributes nothing to the denominator —
the genuine producer error simply vanishes from the metric. As the attacker gets
better at evading ground truth, the reported catch rate can stay flat or RISE.

These tests drive the real ``compute_metrics`` with seeded verdicts (no LLM, no mocks
of the function under test) to make the blind spot undeniable and regression-locked.
The first test characterises the current behaviour (passes); the second asserts the
property the metric SHOULD have and is marked ``xfail`` because the architecture has a
single ground-truth source, so it cannot hold without a design change (a second,
independent ground truth + an explicit "evaded ground truth" counter that raises
alarm). When that fix lands, the strict xfail flips to XPASS and forces removal.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.measure.metrics import compute_metrics
from shared.persistence.models import AttackRow, Run, VerdictRow
from tests.conftest import run_db

# Each white-box round is (held_out_fired, ensemble_caught). Every round below
# represents a GENUINE producer error (a missed fraud); whether the metric can SEE it
# depends entirely on whether the held-out oracle happened to fire.
WEAK_ATTACKER = (  # clumsy: held-out catches 8/10 of its frauds
    [(True, True)] * 4 + [(True, False)] * 4 + [(False, False)] * 2
)
STRONG_ATTACKER = (  # sophisticated: evades held-out on 8/10
    [(True, True)] * 2 + [(False, False)] * 8
)


async def _seed_run(
    session: AsyncSession, run_id: str, rounds: list[tuple[bool, bool]]
) -> None:
    session.add(Run(
        id=run_id, status="complete", target_kind="fraud", shape="shape1_ml",
        budget_rounds=len(rounds), budget_dollars=1.0, white_box_recall=None,
    ))
    await session.flush()  # the run must exist before its attacks/verdicts (FK)
    for i, (held_out_fired, caught) in enumerate(rounds):
        attack_id = f"{run_id}-atk-{i}"
        session.add(AttackRow(
            id=attack_id, run_id=run_id, round_index=i, tactic="t", payload={},
            white_box=True, pillar="red",
        ))
        votes: list[dict[str, object]] = [
            {"oracle": "held_out", "fired": held_out_fired, "weight": 1.0},
        ]
        if caught:  # a second independent oracle corroborated -> tally reaches 2.0
            votes.append({"oracle": "differential", "fired": True, "weight": 1.0})
        session.add(VerdictRow(
            id=f"{run_id}-vdt-{i}", run_id=run_id, attack_id=attack_id,
            producer_output={"label": 0, "fraud_probability": 0.1}, votes=votes,
            tally=2.0 if caught else 1.0, threshold=2.0,
            outcome="caught" if caught else "clean", pillar="oracles",
        ))


def test_held_out_abstentions_vanish_from_producer_wrong() -> None:
    """Characterisation: genuine producer errors that the held-out oracle misses are
    excluded from the metric's denominator entirely (the blind spot)."""

    async def work(session: AsyncSession) -> dict[str, Any]:
        await _seed_run(session, "run-weak", WEAK_ATTACKER)
        return await compute_metrics(session, run_id="run-weak")

    m = run_db(work)
    wb = m["detail"]["white_box"]
    # 10 genuine errors were seeded, but the 2 the held-out oracle missed are invisible.
    assert wb["producer_wrong"] == 8, "held-out abstentions must drop out of the denominator"
    assert m["tiles"]["white_box_catch_rate"] == pytest.approx(4 / 8)


@pytest.mark.xfail(
    strict=True,
    reason="Finding #1: catch-rate denominator is conditioned on the ground-truth "
    "oracle firing, so evading it raises the reported score. Needs a second "
    "independent ground truth + an 'evaded ground truth' counter to fix.",
)
def test_evading_ground_truth_must_not_inflate_catch_rate() -> None:
    """Desired property: a white-box attacker that causes MORE genuine, undetected
    producer errors must not be rewarded with a HIGHER reported catch rate.

    Both runs seed 10 genuine missed-fraud attacks. The strong attacker leaves 8
    genuine errors undetected vs the weak attacker's 6 — strictly worse for the system
    — yet today's metric reports a higher white-box catch rate for it (1.0 vs 0.5).
    """

    async def work(session: AsyncSession) -> tuple[float, float]:
        await _seed_run(session, "run-weak", WEAK_ATTACKER)
        await _seed_run(session, "run-strong", STRONG_ATTACKER)
        weak = await compute_metrics(session, run_id="run-weak")
        strong = await compute_metrics(session, run_id="run-strong")
        return (weak["tiles"]["white_box_catch_rate"],
                strong["tiles"]["white_box_catch_rate"])

    weak_rate, strong_rate = run_db(work)
    assert strong_rate <= weak_rate, (
        f"evading ground truth raised the catch rate: weak={weak_rate} strong={strong_rate}"
    )
