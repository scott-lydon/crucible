"""Seeded-hack corpus export (spec US-11). The corpus is the attacks that genuinely
succeeded: the producer was wrong by ground truth (the held-out oracle fired) AND the
oracle ensemble failed to catch it (the verdict was not "caught"). That is an
undetected hack — the benchmark that outlives the demo. Streamed as JSONL."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.persistence.models import AttackRow, VerdictRow


def _held_out_fired(votes: Sequence[Mapping[str, Any]]) -> bool:
    return any(v.get("oracle") == "held_out" and v.get("fired") for v in votes)


async def export_corpus(session: AsyncSession, run_id: str | None = None) -> list[dict[str, Any]]:
    vq = select(VerdictRow)
    aq = select(AttackRow)
    if run_id is not None:
        vq = vq.where(VerdictRow.run_id == run_id)
        aq = aq.where(AttackRow.run_id == run_id)
    verdicts = {v.attack_id: v for v in (await session.execute(vq)).scalars().all()}
    attacks = list((await session.execute(aq)).scalars().all())

    corpus: list[dict[str, Any]] = []
    for attack in attacks:
        verdict = verdicts.get(attack.id)
        if verdict is None:
            continue
        # An undetected hack: producer wrong by ground truth, ensemble missed it.
        if _held_out_fired(verdict.votes) and verdict.outcome != "caught":
            corpus.append({
                "attack_id": attack.id,
                "run_id": attack.run_id,
                "target_type": "fraud",
                "tactic": attack.tactic,
                "white_box": attack.white_box,
                "payload": dict(attack.payload),
                "producer_output": dict(verdict.producer_output),
                "tally": verdict.tally,
                "captured_at": attack.created_at.isoformat(),
            })
    return corpus
