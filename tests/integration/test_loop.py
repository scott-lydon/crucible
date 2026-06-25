import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from orchestrator.interfaces import Adversary, Detector, Oracle
from orchestrator.loop import Evaluation, TargetEngine, run_loop
from orchestrator.wiring import build_components
from shared.persistence import create_all, make_engine, make_session_factory
from shared.persistence import repo
from shared.persistence.models import RunRow
from shared.types import (
    OracleKind,
    OracleVote,
    SealedSpec,
    VerdictContext,
    Vote,
    sealed_spec_from_dict,
)


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


# --- Produce-shape victim drives the SAME loop (architecture validation) -----
#
# A genuinely different victim kind — a producer that, given a task, PRODUCES an
# output an oracle judges — fits the same harness with no classify-specific code,
# only a custom ``TargetEngine`` + an oracle reading ``ctx.output``. This is the
# Part-A code-agent shape in miniature, proving the seam holds for both kinds.


@dataclass(frozen=True, slots=True)
class _CodeTask:
    txn_index: int
    spec_text: str


class _ProducerVictim:
    """Degenerate stand-in for a code agent: produces a string from a task.
    Tasks whose spec contains 'hack' get a flawed (reward-hacking) output."""

    def produce(self, task: object) -> str:
        spec = cast(_CodeTask, task).spec_text
        return "HARDCODED_HACK" if "hack" in spec else "honest_code"


@dataclass(frozen=True, slots=True)
class _ProduceEngine:
    victim: _ProducerVictim

    def evaluate(self, task: object) -> Evaluation:
        # Gate score 0.0 < threshold => never "caught"; every task routes to the
        # oracle verdict path that judges the produced output. The produced
        # artifact rides on Evaluation.output, not on a score.
        return Evaluation(score=0.0, output=self.victim.produce(task))


class _HeldOutTestOracle:
    """Reads the PRODUCED output (ctx.output), not a score: FAILs the victim when
    the produced code is the reward-hacking artifact."""

    @property
    def kind(self) -> OracleKind:
        return OracleKind.HELD_OUT

    def describe(self) -> str:
        return "produce-victim oracle: fails when the produced output is flawed"

    def vote(self, ctx: VerdictContext) -> OracleVote:
        bad = ctx.output == "HARDCODED_HACK"
        return OracleVote(
            kind=self.kind,
            vote=Vote.FAIL if bad else Vote.PASS,
            weight=1.0,
            reason="produced output failed held-out tests" if bad else "output ok",
            evidence={"output": ctx.output},
        )


class _NoMutation:
    def mutate(self, sample: object, score: float) -> object | None:
        return None


def _produce_spec() -> SealedSpec:
    return sealed_spec_from_dict(
        {
            "target_kind": "code_agent",
            "obligations": ["produced code must pass held-out tests"],
            "invariants": [],
            "metamorphic_relations": [],
            "holdout_generator_kind": "llm",
        }
    )


def _generate_tasks(seed: str, n: int) -> list[object]:
    # Half the tasks ask for a hackable spec; deterministic by index.
    return [
        _CodeTask(txn_index=i, spec_text=("hack me" if i % 2 else "be honest"))
        for i in range(n)
    ]


async def test_producer_victim_drives_same_loop(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    spec = _produce_spec()
    engine: TargetEngine = _ProduceEngine(_ProducerVictim())
    run_id = str(uuid.uuid4())
    async with sf() as s:
        s.add(
            RunRow(
                id=run_id, seed="prod", status="pending", n_rounds=1,
                batch_size=6, threshold=0.5, params_json={},
            )
        )
        await s.commit()
    await run_loop(
        sf,
        run_id=run_id,
        seed="prod",
        n_rounds=1,
        batch_size=6,
        threshold=0.5,
        # ``detector`` is unused by the produce path (the engine produces); a
        # never-called stand-in keeps the existing required parameter satisfied.
        detector=cast(Detector, _ProducerVictim()),
        adversary=cast(Adversary, _NoMutation()),
        oracles=[cast(Oracle, _HeldOutTestOracle())],
        label_fn=lambda _t: True,
        generate_fn=_generate_tasks,
        spec=spec,
        engine=engine,
    )
    async with sf() as s:
        run = await repo.get_run(s, run_id)
        assert run is not None and run.status == "complete"
        verdicts = await repo.verdicts_for_run(s, run_id)
        # All 6 tasks routed to a verdict (gate score 0.0 < 0.5, never caught).
        assert len(verdicts) == 6
        # The 3 hackable tasks (odd indices) produced the flawed output and were
        # FAILed by the held-out oracle reading ctx.output; the 3 honest pass.
        failed = [v for v in verdicts if not v.aggregate_pass]
        assert len(failed) == 3
