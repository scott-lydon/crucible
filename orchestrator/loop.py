import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol, cast

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
from shared.types import SealedSpec, TxnSlice, Origin, VerdictContext

LabelFn = Callable[[object], bool]
GenerateFn = Callable[[str, int], list[object]]


@dataclass(frozen=True, slots=True)
class Evaluation:
    """The result of running the victim on one task: what it PRODUCED, a scalar
    the loop compares to ``threshold`` to decide "caught", and the produced
    artifact for the oracles.

    For the fraud classifier (degenerate producer) ``score`` IS the produced
    output and ``output`` is ``None`` — keeping the persisted row + every fraud
    oracle's view byte-identical. A produce-victim returns its produced artifact
    in ``output`` and a scalar gate in ``score`` (e.g. 0.0 vs a 0.5 threshold to
    always route through the oracle verdict path).
    """

    score: float
    output: object | None


class TargetEngine(Protocol):
    """The target-shaped seam the generic loop delegates to.

    The loop owns persistence, slicing, the adversary call and the oracle
    aggregation — all victim-agnostic. Everything that depends on whether the
    victim CLASSIFIES or PRODUCES is isolated behind this protocol, so a
    produce-victim (code agent) drives the SAME loop by supplying a different
    engine. ``ClassifyEngine`` is the fraud adapter and reproduces today's exact
    behavior.
    """

    def evaluate(self, task: object) -> Evaluation:
        """Run the victim on ``task``; return its produced output + gate score."""
        ...


@dataclass(frozen=True, slots=True)
class ClassifyEngine:
    """Degenerate-producer adapter for a classifier ``Detector`` (the fraud path).

    ``evaluate`` returns ``score = detector.score(task)`` and ``output=None`` —
    exactly the value the loop persisted before this seam existed, so fraud
    behavior is unchanged. A produce-victim ships its own ``TargetEngine`` whose
    ``evaluate`` runs the producer and carries the artifact in ``output``.
    """

    detector: Detector

    def evaluate(self, task: object) -> Evaluation:
        return Evaluation(score=self.detector.score(task), output=None)


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
    spec: SealedSpec,
    engine: "TargetEngine | None" = None,
) -> None:
    # The loop is generic over the produce shape: it delegates "run the victim on
    # a task" to a ``TargetEngine``. ``engine=None`` wraps the classifier
    # ``detector`` in the degenerate-producer ``ClassifyEngine`` — byte-identical
    # to the pre-seam fraud path. A produce-victim (code agent) passes its own
    # engine to drive this SAME loop. ``detector`` stays in the signature both for
    # backward compatibility and because the default engine needs it.
    target: TargetEngine = engine if engine is not None else ClassifyEngine(detector)
    try:
        batch: list[object] = generate_fn(seed, batch_size)
        # deterministic split: even indices = validation, odd = holdout
        slices: dict[int, TxnSlice] = {
            i: (TxnSlice.VALIDATION if i % 2 == 0 else TxnSlice.HOLDOUT)
            for i in range(len(batch))
        }
        # `txn_index` is a convention shared by harness + victim sample records.
        current: dict[int, object] = {
            cast(int, getattr(t, "txn_index")): t for t in batch
        }
        # track which indices have been mutated (and their pre-mutation score)
        prev_score: dict[int, float] = {}

        for round_index in range(n_rounds):
            round_id = str(uuid.uuid4())
            async with session_factory() as s:
                s.add(RoundRow(id=round_id, run_id=run_id, round_index=round_index))
                await s.commit()

            for idx in sorted(current):
                txn = current[idx]
                evaluation = target.evaluate(txn)
                score = evaluation.score
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
                            features_json=asdict(cast(Any, txn)),
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

                # adversary acts only on caught true-positives in the holdout slice
                if caught and label_fn(txn) and slices[idx] is TxnSlice.HOLDOUT:
                    mutated = adversary.mutate(txn, score)
                    if mutated is not None:
                        post_score = target.evaluate(mutated).score
                        async with session_factory() as s:
                            s.add(
                                AttackRow(
                                    id=str(uuid.uuid4()),
                                    run_id=run_id,
                                    round_id=round_id,
                                    txn_id=txn_row_id,
                                    parent_txn_id=txn_row_id,
                                    mutation_json={
                                        "from_features": asdict(cast(Any, txn)),
                                        "to_features": asdict(cast(Any, mutated)),
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

                # verdict for samples the detector let through (not caught)
                if not caught:
                    original_sample = batch[idx] if idx in prev_score else None
                    ctx = VerdictContext(
                        sample=txn,
                        detector_score=score,
                        threshold=threshold,
                        true_label=label_fn(txn),
                        original_sample=original_sample,
                        original_score=prev_score.get(idx),
                        spec=spec,
                        # ``None`` for the fraud classifier (its output IS the
                        # score); a produce-victim's artifact for its oracles.
                        output=evaluation.output,
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
                        # Flush the parent verdict before its child votes so the
                        # FK target exists when the votes batch-inserts. SQLite
                        # leaves FKs unenforced, but Postgres enforces them and
                        # SQLAlchemy does not order INSERTs across tables within a
                        # single flush — without this, oracle_votes can hit the DB
                        # before its verdict row. (Dialect-parity fix.)
                        await s.flush()
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
