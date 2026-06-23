import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.persistence import make_engine, make_session_factory, create_all
from shared.persistence.models import RunRow, RoundRow, TransactionRow, AttackRow
from modules.measure.metrics import compute_run_metrics


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
