import re
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modules.measure.risk_report import NOT_MEASURED, render_risk_report
from shared.persistence import create_all, make_engine, make_session_factory
from shared.persistence.models import (
    AttackRow,
    RoundRow,
    RunRow,
    TransactionRow,
    VerdictRow,
    WhiteBoxMetricsRow,
)
from shared.persistence import repo

_REF = re.compile(r"\[(run|verdict|white_box_metrics|blue_round):([^\]]+)\]")


@pytest.fixture
async def sf() -> async_sessionmaker[AsyncSession]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    return make_session_factory(engine)


async def test_missing_run_returns_none(sf: async_sessionmaker[AsyncSession]) -> None:
    async with sf() as s:
        assert await render_risk_report(s, "missing") is None


async def test_empty_run_renders_not_measured(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    rid = str(uuid.uuid4())
    async with sf() as s:
        s.add(RunRow(id=rid, seed="s", status="complete", n_rounds=1, batch_size=2,
                     threshold=0.5, params_json={"target": "sparkov"}))
        await s.commit()
        md = await render_risk_report(s, rid)
    assert md is not None
    # honest empty-state for unmeasured numbers, never 0.0
    assert NOT_MEASURED in md
    assert "## 1. Purpose" in md and "## 6. Governance" in md


async def _seed_full_run(sf: async_sessionmaker[AsyncSession]) -> str:
    rid = str(uuid.uuid4())
    round0 = str(uuid.uuid4())
    async with sf() as s:
        s.add(RunRow(id=rid, seed="s", status="complete", n_rounds=2, batch_size=4,
                     threshold=0.5, params_json={"target": "sparkov"}))
        s.add(RoundRow(id=round0, run_id=rid, round_index=0))
        # a holdout fraud caught -> baseline/detection numbers exist
        s.add(TransactionRow(id="t1", run_id=rid, round_id=round0, txn_index=1,
              features_json={"amt": 100.0}, true_label=True, origin="synthetic",
              txn_slice="holdout", parent_txn_id=None, detector_score=0.9,
              caught=True, seed="s"))
        s.add(TransactionRow(id="t2", run_id=rid, round_id=round0, txn_index=2,
              features_json={"amt": 100.0}, true_label=True, origin="synthetic",
              txn_slice="validation", parent_txn_id=None, detector_score=0.9,
              caught=True, seed="s"))
        s.add(VerdictRow(id="v1", run_id=rid, round_id=round0, txn_id="t1",
              aggregate_pass=False, fail_weight=0.9, pass_weight=0.1,
              audit_trace_json={}, seed="s"))
        s.add(AttackRow(id="a1", run_id=rid, round_id=round0, txn_id="t1",
              parent_txn_id="t1", mutation_json={}, pre_score=0.9, post_score=0.2,
              evaded=True, true_label_preserved=True, seed="s"))
        await s.commit()
        await repo.upsert_white_box_metrics(s, WhiteBoxMetricsRow(
            run_id=rid, white_box_run_id="wb", black_box_catch_rate=0.8,
            white_box_catch_rate=0.6, white_box_gap=0.2))
    return rid


async def test_numbers_carry_resolvable_row_refs(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    rid = await _seed_full_run(sf)
    async with sf() as s:
        md = await render_risk_report(s, rid)
        assert md is not None
        refs = _REF.findall(md)
        assert refs, "report must carry source-row references"
        # every white_box_metrics ref resolves to a real row
        for kind, row_id in refs:
            if kind == "white_box_metrics":
                assert await repo.white_box_metrics_for_run(s, row_id) is not None
            if kind == "run":
                assert await repo.get_run(s, row_id) is not None
    # the measured white-box numbers are rendered with their references
    assert "0.8000 [white_box_metrics:" in md
    assert "0.6000 [white_box_metrics:" in md
