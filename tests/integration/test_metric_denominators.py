"""Issues #8 and #9 (Gustavo / Measure lane).

#8 — FIXED: ``modules/measure/metrics.py`` previously computed ``undetected_hack_rate =
1 - overall.rate`` over ALL verdicts (black-box + white-box). Black-box attacks
(attacker blind to the scheme) are easier to catch, so the most prominent risk tile was
the optimistic blend while the pessimistic white-box reality lived in a separate tile.
It now reports ``1 - white_box_catch_rate`` whenever a white-box pass ran (falling back
to the overall blend only when no white-box data exists), so the headline can never be
more optimistic than the known worst case (US-10 "honest dashboard").

#9 — RESOLVED as by-design. The cr-f1 trust score is a per-attack SYSTEM-RELIABILITY
rate: ``1 - silent_failures / attacks`` ("how often does the producer silently fail per
attack thrown"). That is the metric we want. The earlier concern — that padding the run
with attacks the held-out oracle cannot verify would inflate the score — does not occur
for the fraud target: the red agent draws white-box attacks from the held-out labelled
partition, so held-out participates on every attack (measured 0/15 abstentions). The
denominator is therefore fully ground-truth-verified, not padded. The guard below locks
that property in; a switch to label-less attacks (the only way #9 bites) would fail it.
(Shape-2 agent targets lack perfect ground truth — re-measure there if agent trust ever
becomes a headline.)
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.measure.metrics import compute_metrics
from shared.persistence.models import AttackRow, Run, VerdictRow
from tests.conftest import FRAUD_SPEC_YAML, run_db


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


# --- Issue #9 (RESOLVED): the trust reliability denominator is ground-truth-verified ---
def _run_fraud(client: TestClient, rounds: int = 10) -> str:
    rid: str = client.post("/runs", json={
        "target_kind": "fraud", "shape": "shape1_ml", "spec_yaml": FRAUD_SPEC_YAML,
        "budget_rounds": rounds, "budget_dollars": 1.0,
    }).json()["runId"]
    for _ in range(600):
        if client.get(f"/runs/{rid}").json()["status"] == "complete":
            break
        time.sleep(0.05)
    return rid


def test_trust_denominator_is_ground_truth_verified(client: TestClient) -> None:
    """Issue #9 resolution guard: every white-box attack in the trust (reliability)
    denominator is verified by ground truth — held-out never abstains on a fraud run,
    because the red agent draws attacks from the held-out labelled partition. So the
    per-attack reliability score is not padded with unverifiable 'passes'. If the red
    agent ever emitted label-less attacks, held-out would abstain and this guard would
    fail — the only way the denominator becomes inflated (issue #9)."""
    rid = _run_fraud(client)

    async def fetch(session: AsyncSession) -> list[list[dict[str, Any]]]:
        rows = (
            await session.execute(
                select(VerdictRow.votes)
                .join(AttackRow, VerdictRow.attack_id == AttackRow.id)
                .where(VerdictRow.run_id == rid, AttackRow.white_box.is_(True))
            )
        ).all()
        return [row[0] for row in rows]

    white_box_votes = run_db(fetch)
    assert white_box_votes, "expected a white-box self-test pass with attacks"
    abstained = 0
    for votes in white_box_votes:
        held_out = next((v for v in votes if v.get("oracle") == "held_out"), None)
        if (held_out is not None and not held_out.get("fired")
                and "no held-out ground-truth" in str(held_out.get("observation", ""))):
            abstained += 1
    assert abstained == 0, (
        f"{abstained}/{len(white_box_votes)} white-box attacks had no ground truth — the "
        "trust reliability denominator is no longer fully verified (issue #9 would bite)"
    )
