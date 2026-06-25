"""Server-Sent Events stream for a run in progress (US-2).

``run_event_stream`` tails a run's PERSISTED rows — it polls the DB for new
attacks and verdicts since the last emitted id, emits one SSE event each, and
ends with a terminal ``complete`` event when the run's status is terminal
(``complete``/``failed``). It reads only what the loop already persisted; it
makes NO new LLM calls and runs no part of the loop itself.

Events emitted (each as an SSE ``event:`` + ``data:`` JSON line):
  * ``attack``  — one per persisted ``AttackRow``: carries evaded + the
    attack-success-rate so far (cumulative over attacks seen).
  * ``trace``   — one per persisted ``AttackRow``: the red agent's
    reasoning/rationale text plus the already-persisted cost/token evidence
    where present (a full per-call "Inspect" needs an ``llm_calls`` table — a
    flagged transparency follow-up, NOT built here).
  * ``verdict`` — one per persisted ``VerdictRow``: aggregate pass/fail + the
    detection-rate so far (cumulative fraction of verdicts that passed).
  * ``complete``— once, when the run reaches a terminal status.

Robust + bounded: a short poll interval, a hard wall-clock cap so a stuck run
never streams forever, and a clean close. No external pub/sub.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.persistence import repo
from shared.persistence.models import AttackRow, VerdictRow

# Poll cadence + a hard wall-clock cap. The cap stops a stuck/never-terminal run
# from streaming forever; the client gets a final ``complete`` with timed_out set.
_POLL_INTERVAL_S = 0.2
# A real run is ~3–4 min; the old 60s cap killed the live charts mid-run. 900s
# comfortably covers a full run while still bounding a stuck/never-terminal run
# so the stream always closes cleanly. The terminal-``complete`` early exit
# (below) still ends a finished run's stream promptly, well before this cap.
_MAX_WALL_S = 900.0
_TERMINAL = {"complete", "failed", "stopped"}


def _sse(event: str, payload: dict[str, object]) -> str:
    """Format one SSE message: an ``event:`` line + a single ``data:`` JSON line."""
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def _rationale_of(attack: AttackRow) -> tuple[str | None, dict[str, object]]:
    """Pull the red agent's rationale + any persisted cost/token evidence.

    The mutation payload is target-shaped; the LLM red agent records its
    rationale (and, where the provider returned them, dollars/tokens) inside the
    persisted ``mutation_json``. We surface whatever is present and never invent
    fields — a deterministic-mutator attack simply has no rationale.
    """
    mutation = attack.mutation_json or {}
    rationale = None
    evidence: dict[str, object] = {}
    if isinstance(mutation, dict):
        raw_rationale = mutation.get("rationale")
        if isinstance(raw_rationale, str):
            rationale = raw_rationale
        for key in ("dollars", "input_tokens", "output_tokens", "tokens", "cost"):
            if key in mutation:
                evidence[key] = mutation[key]
    return rationale, evidence


async def _new_attacks(
    s: AsyncSession, run_id: str, seen: set[str]
) -> list[AttackRow]:
    res = await s.execute(
        select(AttackRow)
        .where(AttackRow.run_id == run_id)
        .order_by(AttackRow.created_at, AttackRow.id)
    )
    return [a for a in res.scalars().all() if a.id not in seen]


async def _new_verdicts(
    s: AsyncSession, run_id: str, seen: set[str]
) -> list[VerdictRow]:
    res = await s.execute(
        select(VerdictRow)
        .where(VerdictRow.run_id == run_id)
        .order_by(VerdictRow.created_at, VerdictRow.id)
    )
    return [v for v in res.scalars().all() if v.id not in seen]


async def run_event_stream(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
    *,
    poll_interval_s: float = _POLL_INTERVAL_S,
    max_wall_s: float = _MAX_WALL_S,
) -> AsyncIterator[str]:
    """Yield SSE strings tailing ``run_id`` until its status is terminal.

    Cumulative counters (attacks seen, evasions, verdicts seen, verdicts passed)
    are maintained across polls so each ``attack``/``verdict`` event carries the
    ASR / detection-rate SO FAR. Emits a final ``complete`` event and returns.
    """
    seen_attacks: set[str] = set()
    seen_verdicts: set[str] = set()
    n_attacks = 0
    n_evaded = 0
    n_verdicts = 0
    n_passed = 0

    loop = asyncio.get_event_loop()
    deadline = loop.time() + max_wall_s

    while True:
        async with session_factory() as s:
            attacks = await _new_attacks(s, run_id, seen_attacks)
            verdicts = await _new_verdicts(s, run_id, seen_verdicts)
            run = await repo.get_run(s, run_id)

        for a in attacks:
            seen_attacks.add(a.id)
            n_attacks += 1
            if a.evaded and a.true_label_preserved:
                n_evaded += 1
            asr = n_evaded / n_attacks if n_attacks else None
            yield _sse(
                "attack",
                {
                    "attack_id": a.id,
                    "round_id": a.round_id,
                    "evaded": bool(a.evaded),
                    "true_label_preserved": bool(a.true_label_preserved),
                    "pre_score": a.pre_score,
                    "post_score": a.post_score,
                    "asr_so_far": asr,
                },
            )
            rationale, evidence = _rationale_of(a)
            yield _sse(
                "trace",
                {
                    "attack_id": a.id,
                    "rationale": rationale,
                    "evidence": evidence,
                },
            )

        for v in verdicts:
            seen_verdicts.add(v.id)
            n_verdicts += 1
            if v.aggregate_pass:
                n_passed += 1
            detection = n_passed / n_verdicts if n_verdicts else None
            yield _sse(
                "verdict",
                {
                    "verdict_id": v.id,
                    "round_id": v.round_id,
                    "aggregate_pass": bool(v.aggregate_pass),
                    "fail_weight": v.fail_weight,
                    "detection_rate_so_far": detection,
                },
            )

        status = run.status if run is not None else "unknown"
        if run is None or status in _TERMINAL:
            yield _sse(
                "complete",
                {
                    "run_id": run_id,
                    "status": status,
                    "attacks": n_attacks,
                    "verdicts": n_verdicts,
                    "timed_out": False,
                },
            )
            return

        if loop.time() >= deadline:
            yield _sse(
                "complete",
                {
                    "run_id": run_id,
                    "status": status,
                    "attacks": n_attacks,
                    "verdicts": n_verdicts,
                    "timed_out": True,
                },
            )
            return

        await asyncio.sleep(poll_interval_s)
