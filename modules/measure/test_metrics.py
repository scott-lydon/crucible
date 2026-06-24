import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.persistence import make_engine, make_session_factory, create_all
from shared.persistence import repo
from shared.persistence.models import (
    RunRow, RoundRow, TransactionRow, AttackRow, VerdictRow,
)
from modules.measure.metrics import (
    compute_run_metrics, dollars_per_caught_hack_for_run,
)


@pytest.fixture
async def sf() -> async_sessionmaker[AsyncSession]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    return make_session_factory(engine)


async def test_no_rows_returns_none(sf: async_sessionmaker[AsyncSession]) -> None:
    async with sf() as s:
        assert await compute_run_metrics(s, "missing") is None


async def test_metrics_from_rows(sf: async_sessionmaker[AsyncSession]) -> None:
    rid = str(uuid.uuid4())
    round0 = str(uuid.uuid4())
    async with sf() as s:
        s.add(RunRow(id=rid, seed="s", status="complete", n_rounds=1, batch_size=2,
                     threshold=0.5, params_json={}))
        s.add(RoundRow(id=round0, run_id=rid, round_index=0))
        # one holdout true-fraud, cleared (missed) -> detection 0/1 = 0.0
        s.add(TransactionRow(id="t1", run_id=rid, round_id=round0, txn_index=1,
              features_json={}, true_label=True, origin="synthetic", txn_slice="holdout",
              parent_txn_id=None, detector_score=0.2, caught=False, seed="s"))
        # one attack attempt that evaded and preserved label -> ASR 1/1 = 1.0
        s.add(AttackRow(id="a1", run_id=rid, round_id=round0, txn_id="t1",
              parent_txn_id="t1", mutation_json={}, pre_score=0.8, post_score=0.2,
              evaded=True, true_label_preserved=True, seed="s"))
        await s.commit()
    m = await compute_run_metrics(s, rid)
    assert m is not None
    assert m.per_round[0].asr == 1.0
    assert m.per_round[0].detection_rate == 0.0
    assert m.per_round[0].evasion_rate == 1.0
    assert m.per_round[0].detection_rate + m.per_round[0].evasion_rate == 1.0


async def test_detection_and_asr_none_when_no_holdout_frauds(sf: async_sessionmaker[AsyncSession]) -> None:
    # a round with only a NON-fraud holdout txn and no attacks:
    # detection_rate and asr must be None (the "Not yet measured" empty state), NOT 0.0
    rid = str(uuid.uuid4())
    round0 = str(uuid.uuid4())
    async with sf() as s:
        s.add(RunRow(id=rid, seed="s", status="complete", n_rounds=1,
                     batch_size=2, threshold=0.5, params_json={}))
        s.add(RoundRow(id=round0, run_id=rid, round_index=0))
        s.add(TransactionRow(id="t1", run_id=rid, round_id=round0, txn_index=1,
              features_json={}, true_label=False, origin="synthetic",
              txn_slice="holdout", parent_txn_id=None,
              detector_score=0.1, caught=False, seed="s"))
        await s.commit()
    m = await compute_run_metrics(s, rid)
    assert m is not None
    assert m.per_round[0].detection_rate is None  # not 0.0
    assert m.per_round[0].evasion_rate is None  # not 0.0
    assert m.per_round[0].asr is None
    assert m.baseline_validation_detection is None  # no validation frauds
    assert m.gap is None  # gap is None when baseline is None
    assert m.dollars_per_caught_hack is None  # no caught hacks -> Not yet measured


async def _seed_one_caught_hack(s: AsyncSession, rid: str) -> None:
    """A 2-round run with exactly one caught hack (oracles voted FAIL)."""
    r0, r1 = str(uuid.uuid4()), str(uuid.uuid4())
    s.add(RunRow(id=rid, seed="s", status="complete", n_rounds=2, batch_size=2,
                 threshold=0.5, params_json={}))
    s.add(RoundRow(id=r0, run_id=rid, round_index=0))
    s.add(RoundRow(id=r1, run_id=rid, round_index=1))
    # round 0: caught true-fraud parent (txn_index 1) that the red agent evades.
    s.add(TransactionRow(id="t0", run_id=rid, round_id=r0, txn_index=1,
          features_json={}, true_label=True, origin="synthetic", txn_slice="holdout",
          parent_txn_id=None, detector_score=0.9, caught=True, seed="s"))
    s.add(AttackRow(id="a0", run_id=rid, round_id=r0, txn_id="t0", parent_txn_id="t0",
          mutation_json={}, pre_score=0.9, post_score=0.2, evaded=True,
          true_label_preserved=True, seed="s"))
    # round 1: the mutated, evading child (same txn_index) gets a verdict.
    s.add(TransactionRow(id="t1", run_id=rid, round_id=r1, txn_index=1,
          features_json={}, true_label=True, origin="mutated", txn_slice="holdout",
          parent_txn_id="t0", detector_score=0.2, caught=False, seed="s"))
    s.add(VerdictRow(id="v1", run_id=rid, round_id=r1, txn_id="t1",
          aggregate_pass=False, fail_weight=1.0, pass_weight=0.0,
          audit_trace_json={}, seed="s"))
    await s.commit()


async def test_dollars_per_caught_hack_from_real_llm_calls(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    rid = str(uuid.uuid4())
    async with sf() as s:
        await _seed_one_caught_hack(s, rid)
        # Two recorded LLM calls totalling $0.30 -> /1 caught hack = 0.30.
        await repo.record_llm_call(s, run_id=rid, pillar="judge", model="m",
            prompt="p", system=None, raw_response=None, parsed_output=None,
            input_tokens=10, output_tokens=5, dollars=0.20)
        await repo.record_llm_call(s, run_id=rid, pillar="red", model="m",
            prompt="p", system=None, raw_response=None, parsed_output=None,
            input_tokens=10, output_tokens=5, dollars=0.10)
    async with sf() as s:
        dollars = await dollars_per_caught_hack_for_run(s, rid)
        m = await compute_run_metrics(s, rid)
    assert dollars == pytest.approx(0.30)
    assert m is not None and m.dollars_per_caught_hack == pytest.approx(0.30)


async def test_dollars_per_caught_hack_none_without_calls(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    rid = str(uuid.uuid4())
    async with sf() as s:
        await _seed_one_caught_hack(s, rid)  # caught hack exists, but no LLM calls
    async with sf() as s:
        assert await dollars_per_caught_hack_for_run(s, rid) is None  # not 0.0


async def test_dollars_per_caught_hack_none_without_caught_hacks(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    rid = str(uuid.uuid4())
    async with sf() as s:
        s.add(RunRow(id=rid, seed="s", status="complete", n_rounds=1, batch_size=2,
                     threshold=0.5, params_json={}))
        # An LLM call exists but there are no caught hacks -> honest None.
        await repo.record_llm_call(s, run_id=rid, pillar="judge", model="m",
            prompt="p", system=None, raw_response=None, parsed_output=None,
            input_tokens=10, output_tokens=5, dollars=0.20)
    async with sf() as s:
        assert await dollars_per_caught_hack_for_run(s, rid) is None  # not 0.0
