"""Verification answers to the Slack asks (Gustavo / Measure lane):

  2. Do the FIVE verifiers actually catch bad outputs, or pass everything?
  3. Does halt-certification trigger when white-box recall drops below 0.7?
  4. Does the trust score produce real A-F grades?

Each test is two-sided: an oracle must FIRE on an output it should catch AND stay quiet
on a good one, so a stuck-open or stuck-closed oracle fails. Drives the real oracles,
the real halt_state, and the real compute_trust. (The complementary result — that on
*subtle real* misses the corroborators are largely silent, ~8% — lives in the finding
write-ups; this file proves the panel is not a no-op.)
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.measure.halt import halt_state
from modules.measure.trust import compute_trust
from modules.oracles.differential.oracle import FraudDifferentialOracle
from modules.oracles.held_out.oracle import FraudHeldOutOracle
from modules.oracles.llm_judge.oracle import LLMJudgeOracle
from modules.oracles.metamorphic.oracle import FraudMetamorphicOracle
from modules.oracles.property_fuzz.oracle import FraudPropertyFuzzOracle
from orchestrator.interfaces import Oracle
from shared.datasets.fraud import load_splits
from shared.llm.client import ScriptedLLM
from shared.persistence.models import AttackRow, Run, VerdictRow
from shared.types.core import Attack
from shared.types.enums import Shape
from shared.types.ids import AttackId, RunId
from shared.types.sealed_spec import Obligation, SealedSpec
from tests.conftest import run_db

_SPEC = SealedSpec(
    spec_id="s", target_kind="fraud", shape=Shape.shape1_ml,
    obligations=(Obligation("catch-fraud", "A fraud must score high.", "label_match", {}),),
    invariants=(), holdout_generator_kind="data_partition",
)


def _atk(payload: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> Attack:
    return Attack(AttackId("a"), RunId("r"), 0, "t", payload, "", "seed",
                  metadata=metadata or {})


def _fires(oracle: Oracle, attack: Attack, output: dict[str, Any]) -> bool:
    return asyncio.run(oracle.vote(_SPEC, attack, output)).fired


def test_five_verifiers_each_catch_bad_and_pass_good() -> None:
    """All five panel members fire on a bad output and stay quiet on a good one."""
    splits = load_splits()
    fraud_row = splits.x_holdout.iloc[splits.y_holdout.tolist().index(1)].to_dict()
    # a normal (legit) row the isoforest scores as non-anomalous
    legit_row = next(splits.x_holdout.iloc[i].to_dict()
                     for i, y in enumerate(splits.y_holdout.tolist()) if y == 0)

    # 1) held-out (ground truth): producer missed a known fraud vs producer agreed.
    held_out = FraudHeldOutOracle()
    assert _fires(held_out, _atk(fraud_row, metadata={"true_label": 1}), {"label": 0})
    assert not _fires(held_out, _atk(fraud_row, metadata={"true_label": 1}), {"label": 1})

    # 2) differential (IsolationForest): anomalous input the producer called legit vs
    #    a normal input the producer called legit.
    diff = FraudDifferentialOracle.load(1)
    assert _fires(diff, _atk(fraud_row), {"label": 0})
    assert not _fires(diff, _atk(legit_row), {"label": 0})

    # 3) metamorphic: a producer whose label flips under a +1% Amount scale vs a stable one.
    flips = FraudMetamorphicOracle(
        lambda p: {"label": 1 if float(p.get("Amount", 0)) >= 100 else 0}, ["Amount"])
    stable = FraudMetamorphicOracle(lambda p: {"label": 0}, ["Amount"])
    assert _fires(flips, _atk({"Amount": 99.5}), {"label": 0})       # 99.5 * 1.01 = 100.5 -> flip
    assert not _fires(stable, _atk({"Amount": 99.5}), {"label": 0})

    # 4) property-fuzz: a malformed output (prob out of [0,1]) vs a well-formed producer.
    fuzz = FraudPropertyFuzzOracle(lambda p: {"fraud_probability": 0.3, "label": 0}, ["Amount"])
    assert _fires(fuzz, _atk({"Amount": 10.0}), {"fraud_probability": 1.5, "label": 0})
    assert not _fires(fuzz, _atk({"Amount": 10.0}), {"fraud_probability": 0.3, "label": 0})

    # 5) LLM judge (half-vote): scripted "violation" vs scripted "ok".
    judge_bad = LLMJudgeOracle(ScriptedLLM(lambda s, p: '{"verdict": "violation", "reason": "x"}'))
    judge_ok = LLMJudgeOracle(ScriptedLLM(lambda s, p: '{"verdict": "ok", "reason": "fine"}'))
    assert _fires(judge_bad, _atk({"Amount": 1.0}), {"label": 0})
    assert not _fires(judge_ok, _atk({"Amount": 1.0}), {"label": 0})


def _seed_run_with_recall(
    run_id: str, recall: float
) -> Callable[[AsyncSession], Awaitable[dict[str, Any]]]:
    async def work(session: AsyncSession) -> dict[str, Any]:
        session.add(Run(
            id=run_id, created_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            status="complete", target_kind="fraud", shape="shape1_ml",
            budget_rounds=5, budget_dollars=1.0, white_box_recall=recall,
        ))
        await session.flush()
        return await halt_state(session)
    return work


def test_halt_triggers_when_recall_below_threshold() -> None:
    halt = run_db(_seed_run_with_recall("run-low", 0.69))  # < 0.70 default red line
    assert halt["halted"] is True
    assert halt["white_box_recall"] == pytest.approx(0.69)
    assert "0.69" in halt["message"] and "0.70" in halt["message"]


def test_halt_clears_when_recall_at_or_above_threshold() -> None:
    halt = run_db(_seed_run_with_recall("run-ok", 0.71))  # >= 0.70
    assert halt["halted"] is False


# (white_box, held_out_fired, caught) per attack -> drives compute_trust.
def _seed_trust(
    run_id: str, attacks: list[tuple[bool, bool, bool]]
) -> Callable[[AsyncSession], Awaitable[dict[str, Any]]]:
    async def work(session: AsyncSession) -> dict[str, Any]:
        session.add(Run(id=run_id, status="complete", target_kind="fraud",
                        shape="shape1_ml", budget_rounds=len(attacks), budget_dollars=1.0))
        await session.flush()
        for i, (wb, fired, caught) in enumerate(attacks):
            aid = f"{run_id}-a-{i}"
            session.add(AttackRow(id=aid, run_id=run_id, round_index=i, tactic="t",
                                  payload={}, white_box=wb, pillar="red"))
            votes = [{"oracle": "held_out", "fired": fired, "weight": 1.0}]
            if caught:
                votes.append({"oracle": "differential", "fired": True, "weight": 1.0})
            session.add(VerdictRow(id=f"{run_id}-v-{i}", run_id=run_id, attack_id=aid,
                                   producer_output={"label": 0}, votes=votes,
                                   tally=2.0 if caught else 1.0, threshold=2.0,
                                   outcome="caught" if caught else "clean", pillar="oracles"))
        await session.flush()
        return await compute_trust(session, run_id=run_id)
    return work


def test_trust_score_spans_a_to_f() -> None:
    """The trust score yields real bands, not a single stuck grade."""
    # A: no silent failures (score 100).
    a = run_db(_seed_trust("run-a", [(True, True, True)] * 5))
    # C: one silent failure in three (score 67).
    c = run_db(_seed_trust("run-c", [(True, True, False)] + [(True, True, True)] * 2))
    # F: all silent (score 0).
    f = run_db(_seed_trust("run-f", [(True, True, False)] * 5))
    assert (a["trust_score"], a["band"]) == (100, "A")
    assert (c["trust_score"], c["band"]) == (67, "C")
    assert (f["trust_score"], f["band"]) == (0, "F")
