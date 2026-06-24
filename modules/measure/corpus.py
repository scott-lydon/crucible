"""Weakness-corpus export (spec US-11, generalized cr-f3). The corpus is the attacks that
genuinely succeeded: the producer was wrong by ground truth (the held-out oracle fired) AND
the ensemble failed to catch it (the verdict was not "caught"). That is an undetected hack —
the durable weakness benchmark that outlives the demo. Target-agnostic: the row carries the
real target kind, the adversarial input, and the obligation that was violated. Streamed as
JSONL."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.persistence.models import AttackRow, Run, VerdictRow


def _held_out_fired(votes: Sequence[Mapping[str, Any]]) -> bool:
    return any(v.get("oracle") == "held_out" and v.get("fired") for v in votes)


def _violated_obligation(votes: Sequence[Mapping[str, Any]]) -> str:
    for v in votes:
        if v.get("oracle") == "held_out" and v.get("fired"):
            return str(v.get("obligation", ""))
    return ""


async def export_corpus(session: AsyncSession, run_id: str | None = None) -> list[dict[str, Any]]:
    vq = select(VerdictRow)
    aq = select(AttackRow, Run.target_kind).join(Run, AttackRow.run_id == Run.id)
    if run_id is not None:
        vq = vq.where(VerdictRow.run_id == run_id)
        aq = aq.where(AttackRow.run_id == run_id)
    verdicts = {v.attack_id: v for v in (await session.execute(vq)).scalars().all()}
    rows = (await session.execute(aq)).all()

    corpus: list[dict[str, Any]] = []
    for attack, target_kind in rows:
        verdict = verdicts.get(attack.id)
        if verdict is None:
            continue
        # An undetected hack: producer wrong by ground truth, ensemble missed it.
        if _held_out_fired(verdict.votes) and verdict.outcome != "caught":
            payload = dict(attack.payload)
            corpus.append({
                "attack_id": attack.id,
                "run_id": attack.run_id,
                "target_type": str(target_kind),
                "tactic": attack.tactic,
                "white_box": attack.white_box,
                "input": payload.get("input"),
                "payload": payload,
                "obligation_violated": _violated_obligation(verdict.votes),
                "producer_output": dict(verdict.producer_output),
                "tally": verdict.tally,
                "captured_at": attack.created_at.isoformat(),
            })
    return corpus
