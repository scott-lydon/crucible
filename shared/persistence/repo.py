import uuid
from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from shared.persistence.models import (AttackRow, BlueRoundRow, OracleVoteRow,
                                       RoundRow, RunRow, SpecRow, TransactionRow,
                                       VerdictRow, WhiteBoxMetricsRow)
from shared.types import SealedSpec, sealed_spec_from_dict, sealed_spec_to_dict

async def get_run(s: AsyncSession, run_id: str) -> RunRow | None:
    return await s.get(RunRow, run_id)


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


async def blue_round_for_run(s: AsyncSession, run_id: str) -> BlueRoundRow | None:
    res = await s.execute(
        select(BlueRoundRow)
        .where(BlueRoundRow.run_id == run_id)
        .order_by(BlueRoundRow.created_at.desc()))
    return res.scalars().first()
