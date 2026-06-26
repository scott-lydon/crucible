"""Verification findings #4 & #5 (Gustavo / Measure lane): denominator/slice choices
make two headline numbers optimistic.

#4 — ``modules/measure/metrics.py:60`` computes ``undetected_hack_rate = 1 -
overall.rate`` over ALL verdicts (black-box + white-box). Black-box attacks (attacker
blind to the scheme) are easier to catch, so the most prominent risk tile is the
optimistic blend while the pessimistic white-box reality lives in a separate tile. An
honest headline (US-10) should not understate the known worst case.

#5 — ``modules/measure/trust.py:72`` computes ``silent_failure_rate = silent /
n_attacks`` where ``n_attacks`` is EVERY attack in the slice, not the confirmed-wrong
ones. So the trust score rises when the run is padded with attacks that never trip
ground truth (held-out abstains): the same real silent-failure count yields a higher
score. The headline is inflatable by attack-mix.

Each finding: a passing characterization test pinning today's number, plus a strict
xfail asserting the honesty/robustness property. Real ``compute_metrics`` /
``compute_trust``; no mocks of the unit under test.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.measure.metrics import compute_metrics
from modules.measure.trust import compute_trust
from shared.persistence.models import AttackRow, Run, VerdictRow
from tests.conftest import run_db

# Each attack is (white_box, held_out_fired, caught). held_out_fired == "producer wrong
# by ground truth"; caught == ensemble reached threshold.
def _seed(session: AsyncSession, run_id: str, attacks: list[tuple[bool, bool, bool]]):
    session.add(Run(
        id=run_id, status="complete", target_kind="fraud", shape="shape1_ml",
        budget_rounds=len(attacks), budget_dollars=1.0,
    ))

    async def _go() -> None:
        await session.flush()
        for i, (white_box, held_out_fired, caught) in enumerate(attacks):
            aid = f"{run_id}-a-{i}"
            session.add(AttackRow(
                id=aid, run_id=run_id, round_index=i, tactic="t", payload={},
                white_box=white_box, pillar="red",
            ))
            votes: list[dict[str, object]] = [
                {"oracle": "held_out", "fired": held_out_fired, "weight": 1.0},
            ]
            if caught:
                votes.append({"oracle": "differential", "fired": True, "weight": 1.0})
            session.add(VerdictRow(
                id=f"{run_id}-v-{i}", run_id=run_id, attack_id=aid,
                producer_output={"label": 0, "fraud_probability": 0.1}, votes=votes,
                tally=2.0 if caught else 1.0, threshold=2.0,
                outcome="caught" if caught else "clean", pillar="oracles",
            ))
        await session.flush()

    return _go


# --- Finding #4: undetected-hack rate blends easy black-box with hard white-box -------
# 8 black-box, all genuinely wrong but caught; 4 white-box, genuinely wrong and missed.
_MIXED = [(False, True, True)] * 8 + [(True, True, False)] * 4


def test_undetected_hack_rate_is_diluted_by_black_box() -> None:
    """Characterisation: the headline undetected-hack rate (1/3) is far below the
    white-box reality (white-box catch rate 0.0 => 100% undetected)."""

    async def work(session: AsyncSession) -> dict:
        await _seed(session, "run-mixed", _MIXED)()
        return await compute_metrics(session, run_id="run-mixed")

    m = run_db(work)
    assert m["tiles"]["undetected_hack_rate"] == pytest.approx(1 / 3)  # 4 missed / 12 wrong
    assert m["tiles"]["white_box_catch_rate"] == pytest.approx(0.0)    # white reality: all missed


@pytest.mark.xfail(
    strict=True,
    reason="Finding #4: the headline undetected-hack rate blends easy black-box attacks "
    "in and so understates the white-box worst case (US-10 'honest dashboard'). It "
    "should be the white-box slice, or never more optimistic than 1 - white_box_catch_rate.",
)
def test_undetected_hack_rate_must_not_understate_white_box() -> None:
    """Desired property: the headline undetected-hack rate must not be more optimistic
    than the white-box reality."""

    async def work(session: AsyncSession) -> dict:
        await _seed(session, "run-mixed", _MIXED)()
        return await compute_metrics(session, run_id="run-mixed")

    m = run_db(work)
    white_box_undetected = 1.0 - m["tiles"]["white_box_catch_rate"]
    assert m["tiles"]["undetected_hack_rate"] >= white_box_undetected


# --- Finding #5: trust score inflatable by padding the denominator --------------------
# Lean: 1 silent failure among 3 white-box attacks (the other 2 confirmed-and-caught).
_LEAN = [(True, True, False)] + [(True, True, True)] * 2
# Padded: same 3, plus 6 white-box attacks that trip no ground truth (held-out abstains).
_PADDED = _LEAN + [(True, False, False)] * 6


def test_trust_score_inflated_by_non_confirming_attacks() -> None:
    """Characterisation: padding a run with attacks that never trip ground truth raises
    the trust score even though the real silent-failure count is unchanged (1)."""

    async def work(session: AsyncSession) -> tuple[dict, dict]:
        await _seed(session, "run-lean", _LEAN)()
        await _seed(session, "run-padded", _PADDED)()
        lean = await compute_trust(session, run_id="run-lean")
        padded = await compute_trust(session, run_id="run-padded")
        return lean, padded

    lean, padded = run_db(work)
    assert lean["silent_failures"] == padded["silent_failures"] == 1   # same real failures
    assert lean["trust_score"] == 67    # 1 - 1/3
    assert padded["trust_score"] == 89  # 1 - 1/9 -> inflated by padding


@pytest.mark.xfail(
    strict=True,
    reason="Finding #5: trust score divides silent failures by ALL attacks, so adding "
    "attacks that trip no ground truth inflates it. The score should be robust to "
    "attack-mix padding (denominator should be confirmed-wrong, or the basis fixed).",
)
def test_trust_score_must_be_robust_to_padding() -> None:
    """Desired property: padding a run with non-ground-truth attacks must not raise the
    trust score."""

    async def work(session: AsyncSession) -> tuple[dict, dict]:
        await _seed(session, "run-lean", _LEAN)()
        await _seed(session, "run-padded", _PADDED)()
        lean = await compute_trust(session, run_id="run-lean")
        padded = await compute_trust(session, run_id="run-padded")
        return lean, padded

    lean, padded = run_db(work)
    assert padded["trust_score"] <= lean["trust_score"]
