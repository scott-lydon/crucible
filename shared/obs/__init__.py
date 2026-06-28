"""Observability spine: one writer, three sinks (durable JSONL, raw stdout, pretty
terminal), driven from a single ``emit`` call. Mirrors the 1040 agent's single-writer
``logEvent`` pattern (tax-filing-agent/server/logger.ts). Everything a run produces
flows through here, so the terminal stream, the JSONL trace, and the static site can
never disagree: they are three renderers of one append-only event log."""

from __future__ import annotations

from shared.obs.emit import (
    GLYPHS,
    SCHEMA_VERSION,
    EventType,
    TraceEvent,
    Tracer,
    TraceSinkUnwritableError,
    ascii_tag,
    glyph_for,
    read_trace,
    run_dir_for,
)

__all__ = [
    "GLYPHS",
    "SCHEMA_VERSION",
    "EventType",
    "TraceEvent",
    "TraceSinkUnwritableError",
    "Tracer",
    "ascii_tag",
    "glyph_for",
    "read_trace",
    "run_dir_for",
]
