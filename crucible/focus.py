"""Slice 5b: component focus-fix subcommands.

Every component is invocable in isolation so a broken one is fixed without running the
whole loop. SINGLE CODE PATH (non-negotiable): each subcommand resolves the component
through the SAME wired container the loop uses (``get_container()`` + the same
registry/protocol method), never a parallel "CLI version". A change to a component is
seen identically by the loop and by its subcommand.

The resolver functions (``resolve_oracle`` etc.) are exported so the same-code-path test
can assert the loop and the subcommand resolve the same object."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from orchestrator.interfaces import Oracle, Retargetable
from orchestrator.wiring import Container, get_container
from shared.types.core import Attack
from shared.types.ids import AttackId, RunId, new_id

if TYPE_CHECKING:
    from shared.types.sealed_spec import SealedSpec


def _load_json(path: str) -> Any:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"file not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _spec_for(target_kind: str, spec_path: str | None, container: Container) -> SealedSpec:
    from crucible.specs import resolve_sealed_spec

    target = container.get_target(target_kind)
    return resolve_sealed_spec(target, spec_path)


# --- resolvers (the SAME wiring the loop uses) -----------------------------
def resolve_oracle(target_kind: str, name: str, container: Container) -> Oracle:
    for oracle in container.oracles_for(target_kind):
        if str(oracle.kind) == name:
            return oracle
    raise KeyError(
        f"no oracle {name!r} for target {target_kind!r}; "
        f"have {[str(o.kind) for o in container.oracles_for(target_kind)]}")


def _attack_from(payload: dict[str, Any], target_kind: str) -> Attack:
    return Attack(
        attack_id=AttackId(new_id("atk")), run_id=RunId("run_focus"), round_index=0,
        tactic="focus", payload=payload, rationale="focus run", seed="focus")


# --- handlers --------------------------------------------------------------
def _oracle_run(args: argparse.Namespace) -> int:
    container = get_container()
    oracle = resolve_oracle(args.target, args.name, container)
    spec = _spec_for(args.target, args.spec, container)
    output = _load_json(args.output)

    # Point a re-querying oracle at the run's target, exactly as the loop does.
    if isinstance(oracle, Retargetable):
        oracle.set_resubmit(container.get_target(args.target).submit)

    attack = _attack_from(output.get("_input", {}), args.target)
    vote = asyncio.run(oracle.vote(spec, attack, output))
    print(json.dumps(vote.as_dict(), indent=2))
    return 0


def _red_propose(args: argparse.Namespace) -> int:
    container = get_container()
    spec = _spec_for(args.target, args.spec, container)
    red = container.red_for(args.target)
    attack = asyncio.run(red.propose(spec, RunId("run_focus"), 0, None, white_box=False))
    print(json.dumps({
        "tactic": attack.tactic, "payload": dict(attack.payload),
        "rationale": attack.rationale, "white_box": attack.white_box}, indent=2))
    return 0


def _blue_propose(args: argparse.Namespace) -> int:
    container = get_container()
    blue = container.blue_for(args.target)
    if blue is None:
        print(json.dumps({"error": f"no blue agent registered for {args.target!r}"}))
        return 1
    spec = _spec_for(args.target, args.spec, container)
    missed_raw = _load_json(args.missed)
    missed = [_attack_from(m, args.target) for m in (missed_raw if isinstance(missed_raw, list)
                                                     else [missed_raw])]
    patch = asyncio.run(blue.harden(spec, RunId("run_focus"), missed))
    print(json.dumps({
        "patch_id": patch.patch_id, "summary": patch.summary,
        "validated": patch.validated,
        "safe_before": patch.holdout_detection_before,
        "safe_after": patch.holdout_detection_after}, indent=2))
    return 0


def _verdict_aggregate(args: argparse.Namespace) -> int:
    """Tally a votes file using the SAME aggregation function the loop uses."""
    from modules.oracles.aggregator import aggregate
    from shared.types.core import OracleVote
    from shared.types.enums import OracleKind

    raw = _load_json(args.votes)
    rows = raw if isinstance(raw, list) else raw.get("votes", [])
    votes = tuple(
        OracleVote(
            oracle=OracleKind(r["oracle"]), fired=bool(r["fired"]),
            weight=float(r.get("weight", 1.0)), obligation=str(r.get("obligation", "")),
            observation=str(r.get("observation", "")), reason=str(r.get("reason", "")),
            seed=str(r.get("seed", "")), dollars=float(r.get("dollars", 0.0)))
        for r in rows)
    attack = _attack_from({}, "focus")
    verdict = aggregate(RunId("run_focus"), attack, {}, votes)
    print(json.dumps({
        "outcome": str(verdict.outcome), "tally": verdict.tally,
        "threshold": verdict.threshold, "summary": verdict.audit.summary,
        "fired": verdict.audit.detail["fired"]}, indent=2))
    return 0


def _metrics_compute(args: argparse.Namespace) -> int:
    from crucible.artifacts import RunArtifacts
    from crucible.local_db import init_local_db
    from modules.measure.metrics import compute_metrics
    from shared.persistence.db import session_scope

    arts = RunArtifacts.for_run(args.run)
    db = arts.root / "crucible.db"
    if not db.exists():
        print(json.dumps({"error": f"no run db at {db}; metrics need the run's persisted "
                          "verdicts"}))
        return 1

    async def _go() -> dict[str, Any]:
        await init_local_db(db)
        async with session_scope() as session:
            return await compute_metrics(session, args.run)

    metrics = asyncio.run(_go())
    arts.write_metrics(metrics)
    print(json.dumps(metrics, indent=2))
    return 0


def dispatch_focus(cmd: str, args: argparse.Namespace) -> int:
    if cmd == "oracle":
        return _oracle_run(args)
    if cmd == "red":
        return _red_propose(args)
    if cmd == "blue":
        return _blue_propose(args)
    if cmd == "verdict":
        return _verdict_aggregate(args)
    if cmd == "metrics":
        return _metrics_compute(args)
    raise ValueError(f"unknown focus command {cmd!r}")
