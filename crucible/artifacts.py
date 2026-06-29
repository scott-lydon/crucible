"""Run artifact layout (the "documents produced over time").

Per run, under ``artifacts/runs/<run_id>/``:
  trace.jsonl              full event stream (written by the Tracer, not here)
  eligibility.json         the pre-flight gate verdict
  suitability.json         the soft fit advisor grade
  verdicts/<id>.json       producer output + each oracle vote + tally + replay seed
  metrics.json             asr / recall / gap / spend (real values or explicit null)
  catalog.jsonl            undetected tactics, append-only, outlives the run
  report.md                human run summary
  sr-117.md                model-risk report

A top-level ``artifacts/runs/index.jsonl`` appends one row per run for history.

This module is the single place that knows the layout, so the runner, the report
renderer, and the focus subcommands all agree on where a file lives. Every writer takes
an optional ``tracer`` and fires an ``artifact_written`` event so paths are surfaced
live and at run end."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.obs.emit import Tracer, artifacts_root, run_dir_for
from shared.types.ids import RunId


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str), encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, obj: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(obj, separators=(",", ":"), default=str) + "\n")


@dataclass(frozen=True)
class RunArtifacts:
    """The set of paths for one run. Construct with ``for_run(run_id)``."""

    run_id: str
    root: Path

    @classmethod
    def for_run(cls, run_id: RunId | str) -> RunArtifacts:
        return cls(run_id=str(run_id), root=run_dir_for(run_id))

    # --- paths -------------------------------------------------------------
    @property
    def trace(self) -> Path:
        return self.root / "trace.jsonl"

    @property
    def eligibility(self) -> Path:
        return self.root / "eligibility.json"

    @property
    def suitability(self) -> Path:
        return self.root / "suitability.json"

    @property
    def metrics(self) -> Path:
        return self.root / "metrics.json"

    @property
    def catalog(self) -> Path:
        return self.root / "catalog.jsonl"

    @property
    def report(self) -> Path:
        return self.root / "report.md"

    @property
    def sr117(self) -> Path:
        return self.root / "sr-117.md"

    def verdict(self, verdict_id: str) -> Path:
        return self.root / "verdicts" / f"{verdict_id}.json"

    def verdict_replay(self, verdict_id: str) -> Path:
        return self.root / "verdicts" / f"{verdict_id}.replay.json"

    # --- writers (each surfaces the path via the tracer) -------------------
    def ensure(self) -> RunArtifacts:
        self.root.mkdir(parents=True, exist_ok=True)
        return self

    def write_json(self, path: Path, obj: Any, *, kind: str, tracer: Tracer | None = None) -> Path:
        _write_json(path, obj)
        if tracer is not None:
            tracer.artifact(path, kind=kind)
        return path

    def write_eligibility(self, obj: Any, *, tracer: Tracer | None = None) -> Path:
        return self.write_json(self.eligibility, obj, kind="eligibility", tracer=tracer)

    def write_suitability(self, obj: Any, *, tracer: Tracer | None = None) -> Path:
        return self.write_json(self.suitability, obj, kind="suitability", tracer=tracer)

    def write_metrics(self, obj: Any, *, tracer: Tracer | None = None) -> Path:
        return self.write_json(self.metrics, obj, kind="metrics", tracer=tracer)

    def write_verdict(self, verdict_id: str, obj: Any, *, tracer: Tracer | None = None) -> Path:
        return self.write_json(self.verdict(verdict_id), obj, kind="verdict", tracer=tracer)

    def write_text(self, path: Path, text: str, *, kind: str, tracer: Tracer | None = None) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if tracer is not None:
            tracer.artifact(path, kind=kind)
        return path

    def append_catalog(self, row: Mapping[str, Any], *, tracer: Tracer | None = None) -> None:
        _append_jsonl(self.catalog, row)
        if tracer is not None:
            tracer.artifact(self.catalog, kind="catalog")


def index_path() -> Path:
    return artifacts_root() / "runs" / "index.jsonl"


def append_index(row: Mapping[str, Any]) -> Path:
    path = index_path()
    _append_jsonl(path, row)
    return path


def list_runs() -> list[dict[str, Any]]:
    """Read the index oldest-first. Missing index is an empty list."""
    path = index_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows
