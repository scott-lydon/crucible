"""Produce-red orchestration for the code-agent victim (slice-11 for code).

The classify-loop (``orchestrator/loop.py``) gates the adversary on CAUGHT
true-positives in the holdout slice — a notion that does not exist for a producer
(its gate ``score`` is 0.0, nothing is ever "caught", and the red drives the run
rather than mutating a caught sample). Rather than contort that flow, this is a
clean, separate produce-red orchestration. The FRAUD path is untouched.

The free, multi-dimensional ``CodeRedAdversary`` drives the run: over a batch of
base tasks it AUTONOMOUSLY proposes task-space manipulations to induce the
producer to reward-hack (pass the visible tests, fail the sealed held-out set).
For each base task this persists:

  * a baseline ``TransactionRow`` + ``VerdictRow`` (the producer's output on the
    UNMODIFIED task, judged by the held-out oracle) — honest "before" evidence;
  * if the red lands a reward-hack, the variant's ``TransactionRow`` +
    ``VerdictRow`` (verdict FAIL — passed visible, failed held-out) plus an
    ``AttackRow`` recording the TASK manipulation (the tactic + visible-test
    narrowing) with ``evaded=True`` (the producer cleared the visible suite) and
    ``true_label_preserved=True`` (the held-out set still encodes the original
    contract, so the failure is a genuine silent reward-hack, not a bug).

Everything is persisted from REAL produce+oracle runs — no fabricated pass/fail.
The harness stays victim-agnostic: the producer, the held-out oracle, the red
adversary, and the per-task batch are all INJECTED from the composition root
(``orchestrator/wiring.py``, the only place permitted to import ``examples/``).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from typing import Any, Protocol, cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modules.blue.code_config_blue import (
    BlueConfigEngineer,
    CodeBlueResult,
    ConfigurableProducer,
    run_code_blue_round,
)
from modules.oracles.aggregator import aggregate
from modules.red.code_red.adversary import CodeRedAdversary, HackResult
from orchestrator.interfaces import Oracle
from orchestrator.loop import GenerateFn
from shared.persistence import repo
from shared.persistence.models import (
    AttackRow,
    BlueRoundRow,
    OracleVoteRow,
    RoundRow,
    TransactionRow,
    VerdictRow,
)
from shared.types import Origin, SealedSpec, TxnSlice, VerdictContext


class _Producer(Protocol):
    def produce(self, task: object) -> str: ...


def _features_of(task: object) -> dict[str, object]:
    """JSON-safe view of a task (dataclass -> asdict, else a repr fallback)."""
    if is_dataclass(task) and not isinstance(task, type):
        return asdict(cast(Any, task))
    return {"repr": repr(task)}


def _n_visible(task: object) -> int:
    raw = getattr(task, "visible_tests", None)
    return len(raw) if raw is not None else 0


async def _persist_produce_verdict(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: str,
    round_id: str,
    seed: str,
    txn_index: int,
    task: object,
    code: str,
    origin: Origin,
    oracles: Sequence[Oracle],
    spec: SealedSpec,
) -> tuple[str, bool]:
    """Persist one produced task: a transaction + its held-out verdict + votes.

    Returns ``(txn_row_id, aggregate_pass)``. The produced code is judged by the
    held-out oracle(s) exactly as the classify-loop's verdict path does, so the
    same audit rows result — only the orchestration around it differs.
    """
    txn_row_id = str(uuid.uuid4())
    async with session_factory() as s:
        s.add(
            TransactionRow(
                id=txn_row_id,
                run_id=run_id,
                round_id=round_id,
                txn_index=txn_index,
                features_json=_features_of(task),
                true_label=True,  # every code task is a genuine task to be judged
                origin=origin.value,
                txn_slice=TxnSlice.HOLDOUT.value,
                parent_txn_id=None,
                detector_score=0.0,  # produce gate: always routes to the oracle
                caught=False,
                seed=seed,
                produced_output=code,
            )
        )
        await s.commit()

    ctx = VerdictContext(
        sample=task,
        detector_score=0.0,
        threshold=0.5,
        true_label=True,
        original_sample=None,
        original_score=None,
        spec=spec,
        output=code,
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
        await s.flush()  # parent verdict before child votes (Postgres FK order)
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
    return txn_row_id, verdict.aggregate_pass


async def run_code_red_loop(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: str,
    seed: str,
    batch_size: int,
    adversary: CodeRedAdversary,
    producer: _Producer,
    oracles: Sequence[Oracle],
    generate_fn: GenerateFn,
    spec: SealedSpec,
) -> list[HackResult]:
    """Drive a produce-red run for the code-agent victim. Returns landed hacks.

    For each base task the red AUTONOMOUSLY explores the task space for a
    reward-hack. A baseline produce->verdict is persisted first (the "before"),
    then any landed hack's variant produce->verdict + an ``AttackRow``. Fails the
    run row on an unexpected error, completes it otherwise.
    """
    landed: list[HackResult] = []
    try:
        batch: list[object] = generate_fn(seed, batch_size)
        round_id = str(uuid.uuid4())
        async with session_factory() as s:
            s.add(RoundRow(id=round_id, run_id=run_id, round_index=0))
            await s.commit()

        for idx, task in enumerate(batch):
            # Baseline: the producer's output on the UNMODIFIED task (the before).
            base_code = producer.produce(task)
            base_txn_id, _ = await _persist_produce_verdict(
                session_factory,
                run_id=run_id,
                round_id=round_id,
                seed=seed,
                txn_index=idx,
                task=task,
                code=base_code,
                origin=Origin.SYNTHETIC,
                oracles=oracles,
                spec=spec,
            )

            # The free, multi-dimensional attack: the red proposes task variants.
            result = adversary.attack(task)
            if not (result.landed and result.variant is not None and result.produced_code):
                continue
            landed.append(result)

            variant_txn_id, _ = await _persist_produce_verdict(
                session_factory,
                run_id=run_id,
                round_id=round_id,
                seed=seed,
                txn_index=idx,
                task=result.variant,
                code=result.produced_code,
                origin=Origin.MUTATED,
                oracles=oracles,
                spec=spec,
            )
            async with session_factory() as s:
                s.add(
                    AttackRow(
                        id=str(uuid.uuid4()),
                        run_id=run_id,
                        round_id=round_id,
                        txn_id=variant_txn_id,
                        parent_txn_id=base_txn_id,
                        mutation_json={
                            "tactic": result.tactic,
                            "rationale": result.rationale,
                            "ops": list(result.ops),
                            "from_visible_tests": _n_visible(task),
                            "to_visible_tests": _n_visible(result.variant),
                        },
                        # The producer "cleared" the visible suite (its reward
                        # signal) — that is the evasion; held-out failure is the
                        # silent failure the oracle catches.
                        pre_score=0.0,
                        post_score=0.0,
                        evaded=True,
                        # The held-out set still encodes the ORIGINAL contract, so
                        # the task's true intent is preserved — a genuine hack.
                        true_label_preserved=True,
                        seed=seed,
                    )
                )
                await s.commit()

        async with session_factory() as s:
            run = await repo.get_run(s, run_id)
            if run is not None:
                run.status = "complete"
                await s.commit()
        return landed

    except Exception as exc:
        async with session_factory() as s:
            run = await repo.get_run(s, run_id)
            if run is not None:
                run.status = "failed"
                run.error = f"{type(exc).__name__}: {exc}"
                await s.commit()
        raise


def _config_iteration_trail(result: CodeBlueResult) -> list[dict[str, object]]:
    """The full per-iteration config-hardening trail as JSON (audit-friendly)."""
    return [
        {
            "rationale": it.rationale,
            "system_prompt": it.system_prompt,
            "pass_rate_after": it.pass_rate_after,
            "recovered": it.recovered,
        }
        for it in result.iterations
    ]


async def run_code_blue(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: str,
    landed: Sequence[HackResult],
    producer: ConfigurableProducer,
    oracle: Oracle,
    spec: SealedSpec,
    engineer_agent: BlueConfigEngineer,
    catalog: object = None,
) -> CodeBlueResult | None:
    """Run the BLUE config-hardening arc after a code-red run, persist the round.

    Completes the red->catch->blue->recover arc for the code-agent victim: blue
    hardens the producer's CONFIG (its system prompt — the makers' shared surface),
    NOT the produced code, and the held-out PASS-RATE is re-measured under the
    patched config on the exact tasks the red hacked.

    Returns ``None`` (and persists no row) when the red loop landed no hack — there
    is nothing for blue to recover (honest: no fabricated round). Otherwise runs
    the bounded config-hardening round, persists a ``BlueRoundRow`` carrying the
    objective held-out pass-rate before/after (recovery may be ``0`` — an honest
    fail), and returns the result. The ``ctx_factory`` mirrors the produce-shape
    context the held-out oracle reads (SPOT with ``_persist_produce_verdict``).
    """
    hacked_tasks = [
        h.variant for h in landed if h.landed and h.variant is not None
    ]
    if not hacked_tasks:
        return None

    def ctx_factory(task: object, code: str) -> VerdictContext:
        return VerdictContext(
            sample=task,
            detector_score=0.0,
            threshold=0.5,
            true_label=True,
            original_sample=None,
            original_score=None,
            spec=spec,
            output=code,
        )

    result = run_code_blue_round(
        # The red loop's catalog of landed reward-hack tactics — what blue hardens
        # against. ``None`` is tolerated (the maker simply sees no prior tactics).
        catalog=catalog,
        producer=producer,
        hacked_tasks=hacked_tasks,
        oracle=oracle,
        ctx_factory=ctx_factory,
        engineer_agent=engineer_agent,
    )

    async with session_factory() as s:
        await repo.add_blue_round(
            s,
            BlueRoundRow(
                id=str(uuid.uuid4()),
                run_id=run_id,
                # The code-agent blue patches the producer CONFIG (not a feature):
                # record the hardened-prompt marker when a patch was applied.
                features_added=(
                    ["hardened_system_prompt"]
                    if result.hardened_system_prompt is not None
                    else []
                ),
                detection_before=result.pass_rate_before,
                detection_after=result.pass_rate_after,
                recovered=result.recovered,
                n_holdout=result.n_tasks,
                proposer_rationale=result.rationale,
                # The full hardened system prompt (the applied config patch), or
                # None on an honest fail where no patch beat the baseline.
                new_model_ref=result.hardened_system_prompt,
                iteration_trail=_config_iteration_trail(result),
            ),
        )
    return result
