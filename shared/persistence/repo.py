from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from shared.persistence.models import (AttackRow, BlueRoundRow, OracleVoteRow,
                                       RoundRow, RunRow, TransactionRow,
                                       VerdictRow)

async def get_run(s: AsyncSession, run_id: str) -> RunRow | None:
    return await s.get(RunRow, run_id)

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

async def blue_round_for_run(s: AsyncSession, run_id: str) -> BlueRoundRow | None:
    res = await s.execute(
        select(BlueRoundRow)
        .where(BlueRoundRow.run_id == run_id)
        .order_by(BlueRoundRow.created_at.desc()))
    return res.scalars().first()
