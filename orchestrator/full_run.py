"""Orchestrator-level full-arc flow: red -> verify -> measure -> blue -> recover.

``run_with_blue`` composes the generic ``run_loop`` (red -> verify -> measure,
persisting rounds/attacks/verdicts) with the Option-B blue recovery round.
``run_loop`` itself stays target-agnostic and blue-free; the composition happens
HERE, where the orchestrator already owns the run lifecycle.

After the red loop, this confirms THIS run produced successful evasions
(``evaded AND true_label_preserved``) — proof the red loop found the gap — then
runs the genuine code-engineering blue maker over the victim's RAW data surface:
a bounded raw training sample plus a held-out set of RAW evasions (real
night-hour frauds with ``amt`` lowered, the exact metamorphic evasion). The maker
discovers a transform, the harness sandbox-runs it, retrains, and measures
recovery — iterating with feedback and ALLOWED TO FAIL. The best result plus the
full iteration trail are persisted as a ``BlueRoundRow``.

The harness stays victim-agnostic: the raw rows, the engineered-retrain callback,
and the base/raw feature lists are all INJECTED from the composition root
(``orchestrator/wiring.py``, the only place permitted to import ``examples/``).
"""

import uuid
from collections.abc import Callable, Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modules.blue.code_engineer import BlueCodeEngineer
from modules.blue.loop import BlueResult, run_blue_round
from modules.measure.corpus_exporter import corpus_entries
from modules.measure.halt_rule import evaluate_halt
from modules.measure.metrics import catch_rate_for_run
from orchestrator.interfaces import Adversary, Detector, Oracle
from orchestrator.loop import GenerateFn, LabelFn, run_loop
from shared.persistence import repo
from shared.persistence.models import BlueRoundRow, RunRow, WhiteBoxMetricsRow
from shared.sandbox.base import Sandbox
from shared.types import SealedSpec

# The raw training set for the engineered retrain. ``None`` = the FULL dataset:
# the fraud base rate is ~0.6%. The sandbox VET runs over a small bounded prefix
# (so untrusted-execution cost stays tiny); the trusted retrain then uses the
# whole loaded sample. That sample MUST be bounded: loading the full ~1.3M-row
# dataset (limit=None) OOM-killed the worker subprocess mid-retrain — and because
# run_loop had already marked the run 'complete', the kill silently produced NO
# blue round (no error, no row). A bounded sample still recovers a real share (the
# engineered feature finds the victim's blind signal, e.g. hour); honest, not
# rigged (amt still dominates the model). Keep this comfortably under memory.
_TRAIN_SAMPLE_N: int | None = 5000
_HOLDOUT_N = 200


async def run_with_blue(
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
    catalog: object,
    engineer_agent: BlueCodeEngineer,
    sandbox: Sandbox,
    retrain_engineered_fn: Callable[..., Detector],
    load_raw_rows: Callable[..., list[dict[str, object]]],
    load_holdout_raw_rows: Callable[..., list[object]],
    base_features: Sequence[str],
    raw_columns: Sequence[str],
    raw_label_fn: Callable[[object], bool],
) -> None:
    """Run the full red->verify->measure->blue->recover arc for one run.

    ``run_loop`` is invoked first (and persists rounds/attacks/verdicts as
    today). If the red loop produced successful evasions, the Option-B blue round
    runs over the RAW data surface and is persisted as a ``BlueRoundRow`` (best
    result + the full iteration trail). Recovery is NOT guaranteed.
    """
    await run_loop(
        session_factory,
        run_id=run_id,
        seed=seed,
        n_rounds=n_rounds,
        batch_size=batch_size,
        threshold=threshold,
        detector=detector,
        adversary=adversary,
        oracles=oracles,
        label_fn=label_fn,
        generate_fn=generate_fn,
        spec=spec,
        # Defer the terminal status: run_loop must NOT mark the run 'complete'
        # after the red loop, or the run would read 'complete' while blue is still
        # running for minutes in the worker (which looked like blue never ran). We
        # mark complete below, once the WHOLE arc (incl. blue) finishes.
        mark_complete=False,
    )

    # If the red loop was cooperatively cancelled it left the run terminal-
    # ``stopped``; do NOT run the blue arc or mark complete.
    async with session_factory() as s:
        run = await repo.get_run(s, run_id)
    if run is not None and run.status == "stopped":
        return

    async with session_factory() as s:
        attacks = await repo.attacks_for_run(s, run_id)
    successful = [a for a in attacks if a.evaded and a.true_label_preserved]
    # Blue runs only when the red loop found a gap AND there is a holdout to
    # validate against; otherwise there is honestly no blue row. Either way we
    # fall through to marking the run complete below.
    if successful:
        # The maker works on RAW rows: a BOUNDED training sample (``_TRAIN_SAMPLE_N``
        # — unbounded OOM-killed the worker) and a held-out set of RAW evasions.
        # Seeded off the run seed for reproducibility.
        row_seed = abs(hash(seed)) % (2**31)
        train_rows = load_raw_rows(limit=_TRAIN_SAMPLE_N, seed=row_seed)
        holdout_rows = load_holdout_raw_rows(limit=_HOLDOUT_N, seed=row_seed)
        if holdout_rows:
            result = run_blue_round(
                catalog=catalog,
                base_features=base_features,
                raw_columns=raw_columns,
                train_rows=train_rows,
                holdout_rows=holdout_rows,
                sandbox=sandbox,
                engineer_agent=engineer_agent,
                retrain_engineered_fn=retrain_engineered_fn,
                # The raw holdout carries no derived `hour`; validate against the
                # REAL committed label, not the derived `is_fraud` rule.
                label_fn=raw_label_fn,
                threshold=threshold,
                old_detector=detector,
            )
            v = result.validation
            async with session_factory() as s:
                await repo.add_blue_round(
                    s,
                    BlueRoundRow(
                        id=str(uuid.uuid4()),
                        run_id=run_id,
                        # The engineered feature the BEST iteration added (empty
                        # on an honest fail where nothing recovered).
                        features_added=(
                            [result.feature_name] if result.new_detector else []
                        ),
                        detection_before=v.detection_before,
                        detection_after=v.detection_after,
                        recovered=v.recovered,
                        n_holdout=v.n,
                        proposer_rationale=result.rationale,
                        new_model_ref=None,
                        iteration_trail=_iteration_trail(result),
                    ),
                )

    # The full arc (red -> verify -> measure -> blue) is done: mark terminal now
    # (run_loop deferred it). Never override a cooperatively-``stopped`` run.
    async with session_factory() as s:
        run = await repo.get_run(s, run_id)
        if run is not None and run.status != "stopped":
            run.status = "complete"
            await s.commit()


async def run_white_box_pass(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    black_box_run_id: str,
    seed: str,
    n_rounds: int,
    batch_size: int,
    threshold: float,
    detector: Detector,
    white_box_adversary: Adversary,
    oracles: Sequence[Oracle],
    label_fn: LabelFn,
    generate_fn: GenerateFn,
    spec: SealedSpec,
) -> None:
    """Run the white-box red pass and persist both passes' catch rates + gap.

    The white-box pass is a SECOND full red loop over the same target, but the
    red agent's prompt carries the oracles' verification scheme (an INFORMED
    attacker). It runs as its own run row so its attacks/verdicts are auditable.
    We then compute the platform CATCH RATE for the black-box run and this
    white-box run (fraction of successful evasions the ORACLES caught) and
    persist black/white/gap keyed to the black-box run.

    Sanity: an informed attacker is caught NO MORE OFTEN than an ignorant one,
    so ``white_box_catch_rate <= black_box_catch_rate`` and ``gap >= 0`` on a
    sane run. Runs the same target-agnostic ``run_loop``; recovery/blue is not
    repeated (this pass measures the verifiers against an informed attacker).
    """
    white_box_run_id = str(uuid.uuid4())
    async with session_factory() as s:
        s.add(
            RunRow(
                id=white_box_run_id,
                seed=seed,
                status="running",
                n_rounds=n_rounds,
                batch_size=batch_size,
                threshold=threshold,
                params_json={"pass": "white_box", "black_box_run_id": black_box_run_id},
            )
        )
        await s.commit()

    await run_loop(
        session_factory,
        run_id=white_box_run_id,
        seed=seed,
        n_rounds=n_rounds,
        batch_size=batch_size,
        threshold=threshold,
        detector=detector,
        adversary=white_box_adversary,
        oracles=oracles,
        label_fn=label_fn,
        generate_fn=generate_fn,
        spec=spec,
    )

    # The informed (white-box) pass is institutional memory too: record the
    # strategies it landed under the SAME target_type as the black-box run, so a
    # repeated tactic accumulates reuse_count across both passes (US-6).
    await record_strategies(
        session_factory, white_box_run_id, target_run_id=black_box_run_id
    )

    async with session_factory() as s:
        black = await catch_rate_for_run(s, black_box_run_id)
        white = await catch_rate_for_run(s, white_box_run_id)
        gap = (black - white) if (black is not None and white is not None) else None
        await repo.upsert_white_box_metrics(
            s,
            WhiteBoxMetricsRow(
                run_id=black_box_run_id,
                white_box_run_id=white_box_run_id,
                black_box_catch_rate=black,
                white_box_catch_rate=white,
                white_box_gap=gap,
            ),
        )
        # Re-evaluate the halt red line against this latest white-box recall and
        # persist the flag (US-13): a recall below the threshold halts new launches.
        await evaluate_halt(s)


async def record_strategies(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
    *,
    target_run_id: str | None = None,
) -> None:
    """Persist this run's landed evasions into the cross-run strategy catalog.

    Derives one ``(tactic, target_type, dollars)`` per successful evasion via the
    shared corpus exporter (single point of truth for that derivation), then
    upserts each into ``strategy_catalog`` — a repeated tactic increments
    ``reuse_count`` rather than inserting a duplicate. ``target_run_id`` overrides
    which run supplies the declared ``target_type`` (the white-box pass records
    under the black-box run's target, since its own params carry none).
    """
    async with session_factory() as s:
        entries = await corpus_entries(s, run_id)
        target_type: str | None = None
        if target_run_id is not None:
            run = await repo.get_run(s, target_run_id)
            params = (run.params_json if run is not None else None) or {}
            target_type = str(params.get("target", "unknown"))
        for entry in entries:
            await repo.record_strategy(
                s,
                tactic=entry.tactic,
                target_type=target_type if target_type is not None else entry.target_type,
                run_id=run_id,
                dollars=entry.dollars,
            )


def _iteration_trail(result: BlueResult) -> list[dict[str, object]]:
    """The full per-iteration trail (rationale/code/sandbox_ok/recovered) as JSON."""
    return [
        {
            "rationale": it.rationale,
            "feature_name": it.feature_name,
            "engineer_src": it.engineer_src,
            "sandbox_ok": it.sandbox_ok,
            "error": it.error,
            "detection_after": it.detection_after,
            "recovered": it.recovered,
        }
        for it in result.iterations
    ]
