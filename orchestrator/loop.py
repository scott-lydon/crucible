import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modules.oracles.aggregator import aggregate
from orchestrator.interfaces import Adversary, Detector, Oracle
from shared.persistence import repo
from shared.persistence.models import (
    AttackRow,
    OracleVoteRow,
    RoundRow,
    TransactionRow,
    VerdictRow,
)
from shared.types import Transaction, TxnSlice, Origin, VerdictContext

LabelFn = Callable[[Transaction], bool]
GenerateFn = Callable[[str, int], list[Transaction]]


async def run_loop(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: str,
    seed: str,
    n_rounds: int,
    batch_size: int,
    threshold: float,
    detector: Detector,
    adversary: Adversary,
    oracles: Sequence[Oracle],
    label_fn: LabelFn,
    generate_fn: GenerateFn,
) -> None:
    try:
        batch: list[Transaction] = generate_fn(seed, batch_size)
        # deterministic split: even indices = validation, odd = holdout
        slices: dict[int, TxnSlice] = {
            i: (TxnSlice.VALIDATION if i % 2 == 0 else TxnSlice.HOLDOUT)
            for i in range(len(batch))
        }
        current: dict[int, Transaction] = {t.txn_index: t for t in batch}
        # track which indices have been mutated (and their pre-mutation score)
        prev_score: dict[int, float] = {}

        for round_index in range(n_rounds):
            round_id = str(uuid.uuid4())
            async with session_factory() as s:
                s.add(RoundRow(id=round_id, run_id=run_id, round_index=round_index))
                await s.commit()

            for idx in sorted(current):
                txn = current[idx]
                score = detector.score(txn)
                caught = score >= threshold
                txn_row_id = str(uuid.uuid4())
                origin = Origin.MUTATED if idx in prev_score else Origin.SYNTHETIC

                async with session_factory() as s:
                    s.add(
                        TransactionRow(
                            id=txn_row_id,
                            run_id=run_id,
                            round_id=round_id,
                            txn_index=idx,
                            features_json=asdict(txn),
                            true_label=label_fn(txn),
                            origin=origin.value,
                            txn_slice=slices[idx].value,
                            parent_txn_id=None,
                            detector_score=score,
                            caught=caught,
                            seed=seed,
                        )
                    )
                    await s.commit()

                # adversary acts only on caught true-frauds in the holdout slice
                if caught and label_fn(txn) and slices[idx] is TxnSlice.HOLDOUT:
                    mutated = adversary.mutate(txn, score)
                    if mutated is not None:
                        post_score = detector.score(mutated)
                        async with session_factory() as s:
                            s.add(
                                AttackRow(
                                    id=str(uuid.uuid4()),
                                    run_id=run_id,
                                    round_id=round_id,
                                    txn_id=txn_row_id,
                                    parent_txn_id=txn_row_id,
                                    mutation_json={
                                        "from_amount": txn.amount,
                                        "to_amount": mutated.amount,
                                    },
                                    pre_score=score,
                                    post_score=post_score,
                                    evaded=post_score < threshold,
                                    true_label_preserved=label_fn(mutated),
                                    seed=seed,
                                )
                            )
                            await s.commit()
                        current[idx] = mutated
                        prev_score[idx] = score

                # verdict for transactions the detector let through (not caught)
                if not caught:
                    original_txn = batch[idx] if idx in prev_score else None
                    ctx = VerdictContext(
                        txn=txn,
                        detector_score=score,
                        threshold=threshold,
                        true_label=label_fn(txn),
                        original_txn=original_txn,
                        original_score=prev_score.get(idx),
                    )
                    votes = [o.vote(ctx) for o in oracles]
                    verdict = aggregate(votes)
                    verdict_id = str(uuid.uuid4())
                    async with session_factory() as s:
                        s.add(
                            VerdictRow(
                                id=verdict_id,
                                run_id=run_id,
                                round_id=round_id,
                                txn_id=txn_row_id,
                                aggregate_pass=verdict.aggregate_pass,
                                fail_weight=verdict.fail_weight,
                                pass_weight=verdict.pass_weight,
                                audit_trace_json=verdict.tally,
                                seed=seed,
                            )
                        )
                        for vote in votes:
                            s.add(
                                OracleVoteRow(
                                    id=str(uuid.uuid4()),
                                    verdict_id=verdict_id,
                                    oracle_kind=vote.kind.value,
                                    vote=vote.vote.value,
                                    weight=vote.weight,
                                    reason=vote.reason,
                                    evidence_json=dict(vote.evidence),
                                )
                            )
                        await s.commit()

        async with session_factory() as s:
            run = await repo.get_run(s, run_id)
            if run is not None:
                run.status = "complete"
                await s.commit()

    except Exception as exc:
        async with session_factory() as s:
            run = await repo.get_run(s, run_id)
            if run is not None:
                run.status = "failed"
                run.error = f"{type(exc).__name__}: {exc}"
                await s.commit()
        raise
