import uuid
from collections.abc import Callable, Sequence
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from orchestrator.interfaces import Adversary, Detector, Oracle
from orchestrator.loop import run_loop
from orchestrator.wiring import build_components
from shared.persistence import create_all, make_engine, make_session_factory
from shared.persistence import repo
from shared.persistence.models import RunRow
from shared.types import SealedSpec


@pytest.fixture
async def sf() -> async_sessionmaker[AsyncSession]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    return make_session_factory(engine)


async def test_loop_persists_rows_and_completes(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    comp = build_components(threshold=0.5)
    run_id = str(uuid.uuid4())
    async with sf() as s:
        s.add(
            RunRow(
                id=run_id,
                seed="seed-1",
                status="pending",
                n_rounds=5,
                batch_size=200,
                threshold=0.5,
                params_json={},
            )
        )
        await s.commit()
    await run_loop(
        sf,
        run_id=run_id,
        seed="seed-1",
        n_rounds=5,
        batch_size=200,
        threshold=0.5,
        detector=cast(Detector, comp["detector"]),
        adversary=cast(Adversary, comp["adversary"]),
        oracles=cast(Sequence[Oracle], comp["oracles"]),
        label_fn=cast(Callable[[object], bool], comp["label_fn"]),
        generate_fn=cast(Callable[[str, int], list[object]], comp["generate_fn"]),
        spec=cast(SealedSpec, comp["spec"]),
    )
    async with sf() as s:
        run = await repo.get_run(s, run_id)
        assert run is not None and run.status == "complete"
        assert len(await repo.attacks_for_run(s, run_id)) > 0
        assert len(await repo.verdicts_for_run(s, run_id)) > 0


async def test_replay_is_byte_equal(sf: async_sessionmaker[AsyncSession]) -> None:
    comp = build_components(threshold=0.5)

    async def run_once(rid: str) -> list[tuple[int, float, bool]]:
        async with sf() as s:
            s.add(
                RunRow(
                    id=rid,
                    seed="seed-X",
                    status="pending",
                    n_rounds=3,
                    batch_size=120,
                    threshold=0.5,
                    params_json={},
                )
            )
            await s.commit()
        await run_loop(
            sf,
            run_id=rid,
            seed="seed-X",
            n_rounds=3,
            batch_size=120,
            threshold=0.5,
            detector=cast(Detector, comp["detector"]),
            adversary=cast(Adversary, comp["adversary"]),
            oracles=cast(Sequence[Oracle], comp["oracles"]),
            label_fn=cast(Callable[[object], bool], comp["label_fn"]),
            generate_fn=cast(
                Callable[[str, int], list[object]], comp["generate_fn"]
            ),
            spec=cast(SealedSpec, comp["spec"]),
        )
        async with sf() as s:
            txns = await repo.transactions_for_run(s, rid)
            return sorted(
                (t.txn_index, round(t.detector_score, 9), t.true_label) for t in txns
            )

    a = await run_once(str(uuid.uuid4()))
    b = await run_once(str(uuid.uuid4()))
    assert a == b
