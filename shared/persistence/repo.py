import uuid
from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from shared.persistence.models import (AttackRow, BlueRoundRow, HaltStateRow,
                                       LlmCallRow, OracleVoteRow, RoundRow,
                                       RunRow, SpecRow, StrategyCatalogRow,
                                       TransactionRow, VerdictRow,
                                       WhiteBoxMetricsRow)
from shared.types import SealedSpec, sealed_spec_from_dict, sealed_spec_to_dict

_HALT_SINGLETON = "singleton"

async def get_run(s: AsyncSession, run_id: str) -> RunRow | None:
    return await s.get(RunRow, run_id)


async def recent_runs(s: AsyncSession, limit: int = 50) -> Sequence[RunRow]:
    """The most recent runs, newest first — backs ``GET /runs`` (run picker).

    Ordered by ``created_at`` descending so the launcher can offer past runs to
    open instead of memorizing an id. ``target`` and ``rounds`` for each row come
    from the run's ``params_json``; this returns the raw rows and lets the
    endpoint shape them. Honest empty sequence when no runs exist.
    """
    res = await s.execute(
        select(RunRow).order_by(RunRow.created_at.desc()).limit(limit)
    )
    return res.scalars().all()


# Terminal statuses a run can rest in: a completed/failed/stopped run is final.
TERMINAL_STATUSES = ("complete", "failed", "stopped")


async def request_cancel(s: AsyncSession, run_id: str) -> RunRow | None:
    """Flag a RUNNING run for cooperative cancellation; return the row (or None).

    Sets ``cancel_requested`` and moves a still-running run to the transient
    ``stopping`` status (the loop flips it to the terminal ``stopped`` when it
    next checks the flag). Idempotent and safe on an already-terminal run: the
    flag is set but the terminal status is NOT overwritten, so the caller can
    report the existing terminal status. Returns ``None`` if the run is unknown.
    """
    run = await s.get(RunRow, run_id)
    if run is None:
        return None
    run.cancel_requested = True
    if run.status not in TERMINAL_STATUSES:
        run.status = "stopping"
    await s.commit()
    return run


async def is_cancel_requested(s: AsyncSession, run_id: str) -> bool:
    """Whether a cancel has been requested for ``run_id`` (loop's poll, own session).

    The loop calls this between rounds via its OWN session so the flag is read
    fresh from the DB — that is how the request crosses the worker-subprocess
    boundary. Unknown run => False (nothing to cancel).
    """
    run = await s.get(RunRow, run_id)
    if run is None:
        return False
    await s.refresh(run)
    return bool(run.cancel_requested)


async def store_spec(s: AsyncSession, run_id: str, spec: SealedSpec) -> str:
    """Persist a run's SealedSpec server-side; return its ``spec_id``.

    The spec is serialized to JSON and written with the app's own DB creds
    (in-process). The producer never sees this path — it only ever receives its
    input sample. Returns the generated ``spec_id`` so callers can resolve it.
    """
    spec_id = str(uuid.uuid4())
    s.add(
        SpecRow(
            spec_id=spec_id,
            run_id=run_id,
            spec_json=sealed_spec_to_dict(spec),
        )
    )
    await s.commit()
    return spec_id


async def resolve_spec(s: AsyncSession, spec_id: str) -> SealedSpec:
    """Rehydrate a SealedSpec by ``spec_id`` (server-side, app DB creds).

    Raises ``KeyError`` if no spec row exists for the id — a missing sealed spec
    is a hard error, never a silent default.
    """
    row = await s.get(SpecRow, spec_id)
    if row is None:
        raise KeyError(f"no sealed spec for spec_id {spec_id!r}")
    return sealed_spec_from_dict(row.spec_json)

async def attacks_for_run(s: AsyncSession, run_id: str) -> Sequence[AttackRow]:
    res = await s.execute(select(AttackRow).where(AttackRow.run_id == run_id))
    return res.scalars().all()

async def all_attacks(s: AsyncSession) -> Sequence[AttackRow]:
    res = await s.execute(select(AttackRow))
    return res.scalars().all()

async def all_transactions(s: AsyncSession) -> Sequence[TransactionRow]:
    res = await s.execute(select(TransactionRow))
    return res.scalars().all()

async def all_verdicts(s: AsyncSession) -> Sequence[VerdictRow]:
    res = await s.execute(select(VerdictRow))
    return res.scalars().all()

async def transactions_for_run(s: AsyncSession, run_id: str) -> Sequence[TransactionRow]:
    res = await s.execute(select(TransactionRow).where(TransactionRow.run_id == run_id))
    return res.scalars().all()

async def rounds_for_run(s: AsyncSession, run_id: str) -> Sequence[RoundRow]:
    res = await s.execute(
        select(RoundRow).where(RoundRow.run_id == run_id).order_by(RoundRow.round_index))
    return res.scalars().all()

async def verdicts_for_run(s: AsyncSession, run_id: str) -> Sequence[VerdictRow]:
    res = await s.execute(select(VerdictRow).where(VerdictRow.run_id == run_id))
    return res.scalars().all()

async def votes_for_verdict(s: AsyncSession, verdict_id: str) -> Sequence[OracleVoteRow]:
    res = await s.execute(
        select(OracleVoteRow).where(OracleVoteRow.verdict_id == verdict_id))
    return res.scalars().all()

async def add_blue_round(s: AsyncSession, row: BlueRoundRow) -> None:
    s.add(row)
    await s.commit()

async def upsert_white_box_metrics(s: AsyncSession, row: WhiteBoxMetricsRow) -> None:
    """Persist (or replace) the black-box/white-box catch rates + gap for a run."""
    existing = await s.get(WhiteBoxMetricsRow, row.run_id)
    if existing is not None:
        await s.delete(existing)
        await s.flush()
    s.add(row)
    await s.commit()


async def white_box_metrics_for_run(
    s: AsyncSession, run_id: str
) -> WhiteBoxMetricsRow | None:
    return await s.get(WhiteBoxMetricsRow, run_id)


async def get_halt_state(s: AsyncSession) -> HaltStateRow | None:
    """The persisted halt-state singleton, or ``None`` if never written."""
    return await s.get(HaltStateRow, _HALT_SINGLETON)


async def set_halt_state(
    s: AsyncSession,
    *,
    halted: bool,
    recall: float | None,
    threshold: float | None,
    source_run_id: str | None,
) -> None:
    """Upsert the halt-state singleton (survives restarts)."""
    row = await s.get(HaltStateRow, _HALT_SINGLETON)
    if row is None:
        row = HaltStateRow(id=_HALT_SINGLETON)
        s.add(row)
    row.halted = halted
    row.recall = recall
    row.threshold = threshold
    row.source_run_id = source_run_id
    await s.commit()


async def record_llm_call(
    s: AsyncSession,
    *,
    run_id: str,
    pillar: str,
    model: str,
    prompt: str,
    system: str | None,
    raw_response: str | None,
    parsed_output: str | None,
    input_tokens: int,
    output_tokens: int,
    dollars: float,
) -> str:
    """Persist one LLM completion record; return its generated id.

    Records a call that ALREADY happened (the wrapper calls this AROUND a real
    provider call) — it never makes a model call itself.
    """
    call_id = str(uuid.uuid4())
    s.add(
        LlmCallRow(
            id=call_id,
            run_id=run_id,
            pillar=pillar,
            model=model,
            prompt=prompt,
            system=system,
            raw_response=raw_response,
            parsed_output=parsed_output,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            dollars=dollars,
        )
    )
    await s.commit()
    return call_id


async def llm_calls_for_run(s: AsyncSession, run_id: str) -> Sequence[LlmCallRow]:
    res = await s.execute(
        select(LlmCallRow)
        .where(LlmCallRow.run_id == run_id)
        .order_by(LlmCallRow.created_at)
    )
    return res.scalars().all()


async def get_llm_call(s: AsyncSession, call_id: str) -> LlmCallRow | None:
    return await s.get(LlmCallRow, call_id)


async def record_strategy(
    s: AsyncSession,
    *,
    tactic: str,
    target_type: str,
    run_id: str,
    dollars: float,
) -> None:
    """Upsert one landed evasion strategy into the persisted catalog (US-6).

    Institutional memory ACROSS runs: the first sighting of ``(tactic,
    target_type)`` inserts the row (seeding ``first_run_id`` /
    ``first_discovered_at`` and ``reuse_count == 1``); every later landing of the
    same pair increments ``reuse_count`` and accumulates ``total_dollars``. A
    landing with real (non-zero) cost also bumps ``dollars_samples`` so the
    average is computed only over rows that carried cost — honest ``None`` when
    none ever did.
    """
    row = await s.get(StrategyCatalogRow, (tactic, target_type))
    if row is None:
        row = StrategyCatalogRow(
            tactic=tactic,
            target_type=target_type,
            first_run_id=run_id,
            reuse_count=0,
            total_dollars=0.0,
            dollars_samples=0,
        )
        s.add(row)
    row.reuse_count += 1
    if dollars > 0.0:
        row.total_dollars += dollars
        row.dollars_samples += 1
    await s.commit()


async def catalog_entries(
    s: AsyncSession, target_type: str | None = None
) -> Sequence[StrategyCatalogRow]:
    """The persisted strategy catalog rows, optionally filtered by target type.

    Returns ``[]`` when no strategy has ever been recorded (honest empty catalog —
    never a fabricated row). Ordered most-reused first, then by tactic for a
    stable client-side default.
    """
    stmt = select(StrategyCatalogRow).order_by(
        StrategyCatalogRow.reuse_count.desc(), StrategyCatalogRow.tactic
    )
    if target_type is not None:
        stmt = stmt.where(StrategyCatalogRow.target_type == target_type)
    res = await s.execute(stmt)
    return res.scalars().all()


async def blue_round_for_run(s: AsyncSession, run_id: str) -> BlueRoundRow | None:
    res = await s.execute(
        select(BlueRoundRow)
        .where(BlueRoundRow.run_id == run_id)
        .order_by(BlueRoundRow.created_at.desc()))
    return res.scalars().first()
