"""Slice 5: deterministic replay from files.

``crucible replay <run_id> <verdict_id>`` re-runs the verification ensemble against the
stored producer output and asserts byte-equality with the persisted verdict. With
deterministic oracles the replay is byte-equal; the LLM judge is deterministic in mock
mode, so the default replay is byte-equal too. Emits a ``verdict`` event tagged
``replay=true`` plus the tally delta and writes ``verdicts/<id>.replay.json``."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from crucible.artifacts import RunArtifacts
from crucible.local_db import init_local_db
from shared.obs.emit import EventType, Tracer
from shared.types.ids import AttackId, RunId


def cmd_replay(args: argparse.Namespace) -> int:
    run_id = args.run_id
    verdict_id = args.verdict_id
    arts = RunArtifacts.for_run(run_id)
    stored_path = arts.verdict(verdict_id)
    if not stored_path.exists():
        print(f"no stored verdict at {stored_path}")
        return 1
    stored = json.loads(stored_path.read_text(encoding="utf-8"))

    db = arts.root / "crucible.db"
    if not db.exists():
        print(f"no run db at {db}; replay needs the run's persisted spec + attack")
        return 1

    tracer = Tracer(run_id, arts.root, stream=args.stream, emoji=not args.no_emoji)
    result = asyncio.run(_replay(run_id, verdict_id, stored, db))

    byte_equal = result["byte_equal"]
    tracer.emit(EventType.verdict, {
        "verdict_id": verdict_id, "replay": True, "outcome": result["outcome"],
        "tally": result["tally"], "threshold": result["threshold"],
        "summary": f"replay byte-equal={byte_equal}"})
    arts.write_json(arts.verdict_replay(verdict_id), result, kind="verdict-replay", tracer=tracer)

    print(f"byte-equal: {str(byte_equal).lower()}", file=sys.stderr)
    print(f"tally delta: {result['tally_delta']:.2e}", file=sys.stderr)
    return 0 if byte_equal else 1


async def _replay(run_id: str, verdict_id: str, stored: dict[str, Any], db: Path) -> dict[str, Any]:
    from sqlalchemy import select

    from orchestrator.loop import _retarget_oracles
    from orchestrator.wiring import build_container
    from shared.persistence.db import session_scope
    from shared.persistence.models import AttackRow, Run
    from shared.persistence.resolver import resolve_spec
    from shared.types.core import Attack

    await init_local_db(db)
    container = build_container()

    async with session_scope() as session:
        run = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one()
        spec = await resolve_spec(session, RunId(run_id))
        arow = (await session.execute(
            select(AttackRow).where(AttackRow.id == stored["attack_id"]))).scalar_one()
        attack = Attack(
            attack_id=AttackId(arow.id), run_id=RunId(run_id), round_index=arow.round_index,
            tactic=arow.tactic, payload=dict(arow.payload), rationale=arow.rationale or "",
            seed=arow.seed, white_box=arow.white_box, hybrid=arow.hybrid,
            metadata=dict((arow.audit_trace or {}).get("metadata", {})))

    oracles = container.oracles_for(run.target_kind)
    _retarget_oracles(oracles, container.get_target(run.target_kind))
    verdict = await container.verify(oracles, spec, attack, stored["producer_output"])

    new_votes = [v.as_dict() for v in verdict.votes]
    tally_delta = abs(float(verdict.tally) - float(stored["tally"]))
    # Byte-equality: the votes + tally + outcome serialize identically to the stored ones.
    byte_equal = (
        json.dumps(new_votes, sort_keys=True) == json.dumps(stored["votes"], sort_keys=True)
        and tally_delta < 1e-9
        and str(verdict.outcome) == stored["outcome"])
    return {
        "verdict_id": verdict_id, "replay": True, "byte_equal": byte_equal,
        "tally": float(verdict.tally), "threshold": float(verdict.threshold),
        "outcome": str(verdict.outcome), "tally_delta": tally_delta,
        "votes": new_votes, "stored_tally": float(stored["tally"])}
