"""Issue #8 (Gustavo / Measure lane) — FIXED: the headline undetected-hack rate now
reflects the white-box worst case instead of the optimistic black+white blend.

#8 — ``modules/measure/metrics.py`` previously computed ``undetected_hack_rate = 1 -
overall.rate`` over ALL verdicts (black-box + white-box). Black-box attacks (attacker
blind to the scheme) are easier to catch, so the most prominent risk tile was the
optimistic blend while the pessimistic white-box reality lived in a separate tile. It
now reports ``1 - white_box_catch_rate`` whenever a white-box pass ran (falling back to
the overall blend only when no white-box data exists), so the headline can never be
more optimistic than the known worst case (US-10 "honest dashboard").

#9 — ``modules/measure/trust.py`` still divides silent failures by ALL attacks, so the
trust score is inflatable by padding the run with attacks that trip no ground truth.
That fix is a semantic redefinition of the cr-f1 trust score (it conflicts with the
documented ``test_trust_score.py`` criteria), so it is left as a strict-xfail pending a
spec decision by the Measure owner.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.measure.metrics import compute_metrics
from modules.measure.trust import compute_trust
from shared.persistence.models import AttackRow, Run, VerdictRow
from tests.conftest import run_db


# Each attack is (white_box, held_out_fired, caught). held_out_fired == "producer wrong
# by ground truth"; caught == ensemble reached threshold.
def _seed(
    session: AsyncSession, run_id: str, attacks: list[tuple[bool, bool, bool]]
) -> Callable[[], Awaitable[None]]:
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
            votes: list[dict[str, Any]] = [
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


# --- Issue #8 (FIXED): undetected-hack rate reflects the white-box worst case ----------
# 8 black-box, all genuinely wrong but caught; 4 white-box, genuinely wrong and missed.
_MIXED = [(False, True, True)] * 8 + [(True, True, False)] * 4


def test_undetected_hack_rate_reflects_white_box_worst_case() -> None:
    """The headline undetected-hack rate equals the white-box undetected rate
    (1 - white_box_catch_rate), not the optimistic 1/3 black+white blend."""

    async def work(session: AsyncSession) -> dict[str, Any]:
        await _seed(session, "run-mixed", _MIXED)()
        return await compute_metrics(session, run_id="run-mixed")

    m = run_db(work)
    assert m["tiles"]["white_box_catch_rate"] == pytest.approx(0.0)   # white-box: all missed
    assert m["tiles"]["undetected_hack_rate"] == pytest.approx(1.0)   # not the 1/3 blend
    # Never more optimistic than the white-box reality.
    assert m["tiles"]["undetected_hack_rate"] >= 1.0 - m["tiles"]["white_box_catch_rate"]


# --- Issue #9 (OPEN, spec decision): trust score inflatable by padding -----------------
# Lean: 1 silent failure among 3 white-box attacks (the other 2 confirmed-and-caught).
_LEAN = [(True, True, False)] + [(True, True, True)] * 2
# Padded: same 3, plus 6 white-box attacks that trip no ground truth (held-out abstains).
_PADDED = _LEAN + [(True, False, False)] * 6


def test_trust_score_inflated_by_non_confirming_attacks() -> None:
    """Characterisation of current cr-f1 behaviour: padding a run with attacks that never
    trip ground truth raises the trust score even though the real silent-failure count is
    unchanged (1). Documents the open #9 concern; trust.py is unchanged pending a spec
    decision (changing it would break the documented test_trust_score.py criteria)."""

    async def work(session: AsyncSession) -> tuple[dict[str, Any], dict[str, Any]]:
        await _seed(session, "run-lean", _LEAN)()
        await _seed(session, "run-padded", _PADDED)()
        lean = await compute_trust(session, run_id="run-lean")
        padded = await compute_trust(session, run_id="run-padded")
        return lean, padded

    lean, padded = run_db(work)
    assert lean["silent_failures"] == padded["silent_failures"] == 1   # same real failures
    assert lean["trust_score"] == 67    # 1 - 1/3
    assert padded["trust_score"] == 89  # 1 - 1/9 -> inflated by padding (the open concern)


@pytest.mark.xfail(
    strict=True,
    reason="Issue #9 (OPEN): trust score divides silent failures by ALL attacks, so "
    "padding with non-ground-truth attacks inflates it. The fix (denominator = "
    "confirmed-wrong) redefines the cr-f1 trust score and conflicts with the documented "
    "test_trust_score.py criteria — deferred to a Measure-owner spec decision.",
)
def test_trust_score_must_be_robust_to_padding() -> None:
    """Desired property: padding a run with non-ground-truth attacks must not raise the
    trust score."""

    async def work(session: AsyncSession) -> tuple[dict[str, Any], dict[str, Any]]:
        await _seed(session, "run-lean", _LEAN)()
        await _seed(session, "run-padded", _PADDED)()
        lean = await compute_trust(session, run_id="run-lean")
        padded = await compute_trust(session, run_id="run-padded")
        return lean, padded

    lean, padded = run_db(work)
    assert padded["trust_score"] <= lean["trust_score"]
