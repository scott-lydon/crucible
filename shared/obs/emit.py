"""The single-writer event emitter.

One ``Tracer.emit(type, data)`` call fans out to THREE sinks:

1. Durable artifact: one JSON line appended to ``artifacts/runs/<run_id>/trace.jsonl``
   (append-only, never rewritten, the grader-readable source of truth).
2. Raw structured stdout: one ``json.dumps`` line per event (machine / log-viewer).
3. Pretty live terminal: a human renderer (glyph + summary line) driven off the SAME
   event, behind a stream mode. Never a second code path that can drift.

The ``EventType`` set is closed and mirrors the loop stages. Every type maps to ONE
glyph in :data:`GLYPHS`, defined once next to the enum so the terminal renderer and
the static site read the same table. The JSONL ``type`` field stays plain text so
``jq`` and graders never parse emoji."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, TextIO

from shared.types.ids import RunId

SCHEMA_VERSION = 1


class EventType(StrEnum):
    """Closed set of trace event types. A new loop stage MUST add a member here and a
    glyph in :data:`GLYPHS`; the glyph-table completeness test fails otherwise, which is
    the runtime stand-in for compile-time exhaustiveness."""

    run_start = "run_start"
    eligibility_checked = "eligibility_checked"
    suitability_assessed = "suitability_assessed"
    run_rejected = "run_rejected"
    adapter_scaffolded = "adapter_scaffolded"
    spec_sealed = "spec_sealed"
    round_start = "round_start"
    red_tactic_proposed = "red_tactic_proposed"
    target_queried = "target_queried"
    target_scored = "target_scored"
    oracle_fired = "oracle_fired"
    verdict = "verdict"
    catalog_hit = "catalog_hit"
    blue_patch_proposed = "blue_patch_proposed"
    blue_retrained = "blue_retrained"
    holdout_validated = "holdout_validated"
    metric_update = "metric_update"
    halt_check = "halt_check"
    artifact_written = "artifact_written"
    run_end = "run_end"


# One glyph per EventType. Single source of truth shared by the terminal renderer and
# the static site. oracle_fired renders 🟢/🔴 from its pass/fail payload, so its entry
# here is the neutral "fired" marker.
GLYPHS: dict[EventType, str] = {
    EventType.run_start: "▶",
    EventType.eligibility_checked: "🔎",
    EventType.suitability_assessed: "🧭",
    EventType.run_rejected: "🚫",
    EventType.adapter_scaffolded: "🔌",
    EventType.spec_sealed: "🔒",
    EventType.round_start: "🥊",
    EventType.red_tactic_proposed: "🎯",
    EventType.target_queried: "📡",
    EventType.target_scored: "📊",
    EventType.oracle_fired: "🔬",
    EventType.verdict: "⚖️",
    EventType.catalog_hit: "🧠",
    EventType.blue_patch_proposed: "🔧",
    EventType.blue_retrained: "♻️",
    EventType.holdout_validated: "🛡️",
    EventType.metric_update: "📈",
    EventType.halt_check: "🛑",
    EventType.artifact_written: "📄",
    EventType.run_end: "🏁",
}

# ASCII fallback tag per EventType for terminals that mangle wide glyphs (--no-emoji).
ASCII_TAGS: dict[EventType, str] = {
    EventType.run_start: "[START]",
    EventType.eligibility_checked: "[ELIG]",
    EventType.suitability_assessed: "[FIT]",
    EventType.run_rejected: "[REJECT]",
    EventType.adapter_scaffolded: "[ADAPTER]",
    EventType.spec_sealed: "[SEALED]",
    EventType.round_start: "[ROUND]",
    EventType.red_tactic_proposed: "[RED]",
    EventType.target_queried: "[QUERY]",
    EventType.target_scored: "[SCORE]",
    EventType.oracle_fired: "[ORACLE]",
    EventType.verdict: "[VERDICT]",
    EventType.catalog_hit: "[CATALOG]",
    EventType.blue_patch_proposed: "[BLUE]",
    EventType.blue_retrained: "[RETRAIN]",
    EventType.holdout_validated: "[HOLDOUT]",
    EventType.metric_update: "[METRIC]",
    EventType.halt_check: "[HALT]",
    EventType.artifact_written: "[FILE]",
    EventType.run_end: "[END]",
}


def glyph_for(event_type: EventType) -> str:
    return GLYPHS[event_type]


def ascii_tag(event_type: EventType) -> str:
    return ASCII_TAGS[event_type]


class TraceSinkUnwritableError(RuntimeError):
    """The run directory or trace file could not be written. Names the path and the
    fix instead of silently dropping the event (constitution.md: fail loud)."""

    def __init__(self, path: Path, cause: Exception) -> None:
        super().__init__(
            f"cannot write trace at {path}: {cause}. "
            f"Fix: ensure the parent dir exists and is writable "
            f"(check CRUCIBLE_ARTIFACTS_DIR / disk space / permissions)."
        )
        self.path = path
        self.cause = cause


@dataclass(frozen=True, slots=True)
class TraceEvent:
    ts: float                 # epoch seconds (float, ms precision)
    run_id: str
    type: EventType
    seq: int                  # monotonic per-run counter; total order even within one ms
    schema_version: int
    data: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "run_id": self.run_id,
            "type": str(self.type),     # plain text, never emoji
            "seq": self.seq,
            "schema_version": self.schema_version,
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> TraceEvent:
        return cls(
            ts=float(raw["ts"]),
            run_id=str(raw["run_id"]),
            type=EventType(raw["type"]),
            seq=int(raw["seq"]),
            schema_version=int(raw.get("schema_version", 0)),
            data=dict(raw.get("data", {})),
        )


def artifacts_root() -> Path:
    """Root for all run artifacts. Overridable via CRUCIBLE_ARTIFACTS_DIR so tests and
    sandboxes write to a throwaway location."""
    import os

    return Path(os.environ.get("CRUCIBLE_ARTIFACTS_DIR", "artifacts")).resolve()


def run_dir_for(run_id: RunId | str) -> Path:
    return artifacts_root() / "runs" / str(run_id)


@dataclass
class Tracer:
    """One writer per run. Holds the monotonic seq counter and the stream config, so
    every event for a run is totally ordered and rendered through one path.

    ``stream`` is one of ``human`` | ``json`` | ``both`` | ``none``. ``emoji`` toggles
    the glyph table vs ASCII tags. ``out`` is the human/pretty stream; ``raw_out`` is
    the structured-JSON stream (kept separate so ``--stream json`` can pipe clean)."""

    run_id: str
    run_dir: Path
    stream: str = "human"
    emoji: bool = True
    out: TextIO = field(default_factory=lambda: sys.stderr)
    raw_out: TextIO = field(default_factory=lambda: sys.stdout)
    _seq: int = 0
    _now: Any = None          # injectable clock for deterministic tests

    def __post_init__(self) -> None:
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise TraceSinkUnwritableError(self.run_dir, exc) from exc
        self._trace_path = self.run_dir / "trace.jsonl"

    @property
    def trace_path(self) -> Path:
        return self._trace_path

    def _timestamp(self) -> float:
        return float(self._now()) if self._now is not None else time.time()

    def emit(self, event_type: EventType, data: Mapping[str, Any] | None = None) -> TraceEvent:
        """Append one event to the JSONL trail, echo a raw JSON line, and render the
        pretty line. The single fan-out point: there is no other way to write a trace
        event, so the three sinks can never disagree."""
        event = TraceEvent(
            ts=self._timestamp(),
            run_id=self.run_id,
            type=event_type,
            seq=self._seq,
            schema_version=SCHEMA_VERSION,
            data=dict(data or {}),
        )
        self._seq += 1
        self._write_durable(event)
        self._write_raw(event)
        self._write_human(event)
        return event

    def artifact(self, path: Path | str, kind: str, **extra: Any) -> TraceEvent:
        """Convenience: emit an ``artifact_written`` event carrying the ABSOLUTE path so
        the human renderer and the slash command can surface it as an openable link."""
        abs_path = str(Path(path).resolve())
        return self.emit(EventType.artifact_written, {"path": abs_path, "kind": kind, **extra})

    def _write_durable(self, event: TraceEvent) -> None:
        line = json.dumps(event.to_dict(), separators=(",", ":"), sort_keys=True)
        try:
            with self._trace_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError as exc:
            raise TraceSinkUnwritableError(self._trace_path, exc) from exc

    def _write_raw(self, event: TraceEvent) -> None:
        if self.stream not in ("json", "both"):
            return
        self.raw_out.write(json.dumps(event.to_dict(), separators=(",", ":")) + "\n")
        self.raw_out.flush()

    def _write_human(self, event: TraceEvent) -> None:
        if self.stream not in ("human", "both"):
            return
        self.out.write(self.render_line(event) + "\n")
        self.out.flush()

    def render_line(self, event: TraceEvent) -> str:
        """Render one event as a single human line. Pure on the event, so the static
        site can call the same function over read_trace() and match the terminal."""
        return render_line(event, emoji=self.emoji)


def _marker(event: TraceEvent, emoji: bool) -> str:
    if not emoji:
        return ascii_tag(event.type)
    if event.type is EventType.oracle_fired:
        passed = event.data.get("passed")
        if passed is True:
            return "🟢"
        if passed is False:
            return "🔴"
    return glyph_for(event.type)


def _summary(event: TraceEvent) -> str:
    """A short human summary per event type. Kept data-driven so adding a type does not
    require touching a giant switch; falls back to a compact dump of the payload."""
    d = event.data
    t = event.type
    if t is EventType.run_start:
        return f"run {event.run_id} target={d.get('target')} rounds={d.get('rounds')}"
    if t is EventType.eligibility_checked:
        return f"{d.get('verdict')} — {d.get('reason', '')}".rstrip(" —")
    if t is EventType.suitability_assessed:
        return f"{d.get('grade')} — {d.get('reason', '')}".rstrip(" —")
    if t is EventType.run_rejected:
        return str(d.get("reason", "rejected"))
    if t is EventType.adapter_scaffolded:
        return f"{d.get('project')} -> {d.get('module')}"
    if t is EventType.spec_sealed:
        return f"{d.get('obligations', '?')} obligations, {d.get('invariants', '?')} invariants"
    if t is EventType.round_start:
        return f"round {d.get('round')}" + (" (white-box)" if d.get("white_box") else "")
    if t is EventType.red_tactic_proposed:
        return f"{d.get('tactic')}: {d.get('rationale', '')}"
    if t is EventType.target_queried:
        return f"attack {d.get('attack_id', '')}"
    if t is EventType.target_scored:
        return f"output keys={list(d.get('output', {}))}"
    if t is EventType.oracle_fired:
        verdict = "PASS" if d.get("passed") else "FAIL"
        return f"{d.get('oracle')}: {verdict} — {d.get('reason', '')}".rstrip(" —")
    if t is EventType.verdict:
        tag = " [replay]" if d.get("replay") else ""
        return f"{d.get('outcome')} tally={d.get('tally')}/{d.get('threshold')}{tag}"
    if t is EventType.catalog_hit:
        return f"undetected: {d.get('tactic')}"
    if t is EventType.blue_patch_proposed:
        return str(d.get("summary", "patch"))
    if t is EventType.blue_retrained:
        return f"version {d.get('version')}"
    if t is EventType.holdout_validated:
        return f"before={d.get('before')} after={d.get('after')}"
    if t is EventType.metric_update:
        return (
            f"asr={d.get('asr')} recall={d.get('recall')} "
            f"gap={d.get('gap')} spend=${d.get('spend')}"
        )
    if t is EventType.halt_check:
        return "HALT" if d.get("halt") else "continue"
    if t is EventType.artifact_written:
        return f"{d.get('kind')}: {d.get('path')}"
    if t is EventType.run_end:
        return f"status={d.get('status')}"
    return json.dumps(dict(d), separators=(",", ":"))


def render_line(event: TraceEvent, *, emoji: bool = True) -> str:
    stamp = time.strftime("%H:%M:%S", time.localtime(event.ts))
    return f"{stamp} {_marker(event, emoji)} {event.type}  {_summary(event)}"


def read_trace(run_id: RunId | str, *, run_dir: Path | None = None) -> list[TraceEvent]:
    """Read the append-only trace oldest-first (mirror of the 1040 ``readTrace``).

    A missing trace file is an empty list, not an error (the run may not have started);
    a malformed line raises so corruption is never silently skipped."""
    path = (run_dir or run_dir_for(run_id)) / "trace.jsonl"
    if not path.exists():
        return []
    events: list[TraceEvent] = []
    with path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(TraceEvent.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                raise ValueError(f"corrupt trace line {lineno} in {path}: {exc}") from exc
    return events
