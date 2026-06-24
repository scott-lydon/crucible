import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modules.measure.corpus_exporter import corpus_entries, corpus_jsonl
from shared.persistence import create_all, make_engine, make_session_factory
from shared.persistence.models import (
    AttackRow,
    RoundRow,
    RunRow,
    TransactionRow,
    VerdictRow,
)


@pytest.fixture
async def sf() -> async_sessionmaker[AsyncSession]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    return make_session_factory(engine)


async def _seed_run(sf: async_sessionmaker[AsyncSession]) -> str:
    rid = str(uuid.uuid4())
    round0 = str(uuid.uuid4())
    async with sf() as s:
        s.add(RunRow(id=rid, seed="s", status="complete", n_rounds=2, batch_size=2,
                     threshold=0.5, params_json={"target": "sparkov"}))
        s.add(RoundRow(id=round0, run_id=rid, round_index=0))
        # parent (re-scored) txn for the successful evasion lineage, with amt
        s.add(TransactionRow(id="t1", run_id=rid, round_id=round0, txn_index=7,
              features_json={"txn_index": 7, "amt": 240.0}, true_label=True,
              origin="mutated", txn_slice="holdout", parent_txn_id=None,
              detector_score=0.2, caught=False, seed="s"))
        # the oracle verdict on that re-scored txn = the audit trace
        s.add(VerdictRow(id="v1", run_id=rid, round_id=round0, txn_id="t1",
              aggregate_pass=False, fail_weight=0.9, pass_weight=0.1,
              audit_trace_json={"tally": {"FAIL": 0.9}}, seed="s"))
        # successful attack: evaded AND label preserved, amt lowered (down)
        s.add(AttackRow(id="a1", run_id=rid, round_id=round0, txn_id="t1",
              parent_txn_id="t1",
              mutation_json={"from_features": {"amt": 800.0, "txn_index": 7},
                             "to_features": {"amt": 240.0, "txn_index": 7}},
              pre_score=0.8, post_score=0.2, evaded=True,
              true_label_preserved=True, seed="s"))
        # a FAILED attack (did not evade) -> NOT in corpus
        s.add(AttackRow(id="a2", run_id=rid, round_id=round0, txn_id="t1",
              parent_txn_id="t1", mutation_json={}, pre_score=0.8, post_score=0.9,
              evaded=False, true_label_preserved=True, seed="s"))
        await s.commit()
    return rid


async def test_empty_corpus_is_empty(sf: async_sessionmaker[AsyncSession]) -> None:
    async with sf() as s:
        entries = await corpus_entries(s, "missing")
        lines = [ln async for ln in corpus_jsonl(s, "missing")]
    assert entries == []
    assert lines == []  # empty file, NOT a fabricated row


async def test_only_successful_evasions(sf: async_sessionmaker[AsyncSession]) -> None:
    rid = await _seed_run(sf)
    async with sf() as s:
        entries = await corpus_entries(s, rid)
    assert len(entries) == 1  # the failed attack a2 is excluded
    e = entries[0]
    assert e.attack_id == "a1"
    assert e.target_type == "red"
    assert e.tactic == "amt:down"
    assert e.dollars == 240.0
    assert e.audit_trace == {"tally": {"FAIL": 0.9}}
    assert e.prompt == {"amt": 240.0, "txn_index": 7}


async def test_jsonl_line_count_equals_table_row_count(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    rid = await _seed_run(sf)
    async with sf() as s:
        entries = await corpus_entries(s, rid)
        lines = [ln async for ln in corpus_jsonl(s, rid)]
    # THE US-11 invariant: exactly one JSONL line per table row.
    assert len(lines) == len(entries)
    assert all(ln.endswith("\n") for ln in lines)
