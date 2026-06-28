"""``crucible catalog`` — show the append-only strategy catalog (undetected tactics).

Per-run with ``--run`` (reads that run's ``catalog.jsonl``), else the global distilled
catalog the red agent reuses across runs (``data/strategy_catalog.jsonl``)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from crucible.artifacts import RunArtifacts


def cmd_catalog(args: argparse.Namespace) -> int:
    if args.run:
        path = RunArtifacts.for_run(args.run).catalog
        label = f"run {args.run}"
    else:
        path = Path("data/strategy_catalog.jsonl")
        label = "global strategy catalog"

    if not path.exists():
        print(f"{label}: no catalog yet ({path})")
        return 0

    rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    print(f"{label}: {len(rows)} entr{'y' if len(rows) == 1 else 'ies'} ({path})\n")
    for i, row in enumerate(rows, start=1):
        tactic = row.get("tactic") or row.get("attack_id") or row.get("verdict_id") or "?"
        reuse = row.get("reuse_count")
        suffix = f" (reused x{reuse})" if reuse is not None else ""
        print(f"  {i:>3}. {tactic}{suffix}")
    return 0
