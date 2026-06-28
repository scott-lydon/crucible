"""``crucible status`` — list runs and their last known state, from the artifact files
(never a live server). One run with ``--run`` shows the last trace event in detail."""

from __future__ import annotations

import argparse

from crucible.artifacts import RunArtifacts, list_runs
from shared.obs.emit import read_trace


def cmd_status(args: argparse.Namespace) -> int:
    if args.run:
        events = read_trace(args.run)
        if not events:
            print(f"run {args.run}: no trace found")
            return 1
        arts = RunArtifacts.for_run(args.run)
        last = events[-1]
        print(f"run {args.run}")
        print(f"  events: {len(events)}")
        print(f"  last:   {last.type}  {dict(last.data)}")
        print(f"  dir:    {arts.root}")
        return 0

    rows = list_runs()
    if not rows:
        print("no runs yet (artifacts/runs/index.jsonl is empty)")
        return 0
    print(f"{len(rows)} run(s):\n")
    for row in rows:
        wb = row.get("white_box_catch_rate")
        wb_text = "n/a" if wb is None else f"{wb * 100:.0f}%"
        print(f"  {row.get('run_id'):<24} {row.get('target'):<12} "
              f"{row.get('status'):<10} verdicts={row.get('verdicts', '-')} "
              f"wb_recall={wb_text}")
    return 0
