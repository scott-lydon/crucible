import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modules.oracles.aggregator import aggregate
from orchestrator.interfaces import (
    Adversary,
    Detector,
    Evaluation,
    Oracle,
    TargetEngine,
)
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

# Re-export the produce-shape seam types (defined in ``orchestrator.interfaces``
# so an ``examples/`` victim can construct them without importing this module).
# Callers have always imported them from ``orchestrator.loop``; keep that stable.
__all__ = ["Evaluation", "TargetEngine", "ClassifyEngine", "run_loop"]


def _features_of(task: object) -> dict[str, object]:
    """Serialize a task to a JSON-safe mapping for ``TransactionRow.features_json``.

    Generic over the victim: a dataclass task (both fraud victims, the code task)
    serializes via ``asdict``; any other shape falls back to a safe ``str`` repr
    under a single key rather than crashing the loop. SPOT for task serialization.
    """
    if is_dataclass(task) and not isinstance(task, type):
        return asdict(task)
    return {"repr": repr(task)}


def _output_text(output: object | None) -> str | None:
    """Render a produced artifact to text for ``TransactionRow.produced_output``.

    ``None`` (the fraud classifier, whose output is its score) persists ``None`` —
    keeping that column NULL and the fraud path byte-identical. A produce-victim's
    artifact persists as its string form (already a ``str`` for the code agent).
    """
    if output is None:
        return None
    return output if isinstance(output, str) else repr(output)


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
    detector: Detector | None = None,
    adversary: Adversary,
    oracles: Sequence[Oracle],
    label_fn: LabelFn,
    generate_fn: GenerateFn,
    spec: SealedSpec,
    engine: TargetEngine | None = None,
) -> None:
    # The loop is generic over the produce shape: it delegates "run the victim on
    # a task" to a ``TargetEngine``. ``engine=None`` wraps the classifier
    # ``detector`` in the degenerate-producer ``ClassifyEngine`` — byte-identical
    # to the pre-seam fraud path. A produce-victim (code agent) passes its own
    # ``engine`` and need NOT pass a ``detector`` (its engine produces); a fraud
    # run passes ``detector`` and lets ``engine`` default. Exactly one must be set.
    if engine is None:
        if detector is None:
            raise ValueError("run_loop requires either a detector or an engine")
        target: TargetEngine = ClassifyEngine(detector)
    else:
        target = engine
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
                            features_json=_features_of(txn),
                            true_label=label_fn(txn),
                            origin=origin.value,
                            txn_slice=slices[idx].value,
                            parent_txn_id=None,
                            detector_score=score,
                            caught=caught,
                            seed=seed,
                            # The produced artifact (code-agent source); NULL for
                            # the fraud classifier so its row stays byte-identical.
                            produced_output=_output_text(evaluation.output),
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
                                        "from_features": _features_of(txn),
                                        "to_features": _features_of(mutated),
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
