"""Structured logging. Every log line carries run_id / pillar / subcomponent / seed
where available (plan.md section 10). JSON to stdout in production, captured by the
host. The CLI front-end (crucible/cli.py) configures logging to stderr through a
LazyStderr handle so `crucible run --stream json` keeps stdout a pure event stream."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


class LazyStderr:
    """A file-like object that defers to sys.stderr at WRITE time, not at
    construction. The CLI may run inside a harness (pytest, click groups, custom
    handlers) that reassigns sys.stderr after this object is built; binding
    eagerly would freeze the logger to the wrong handle and silently lose lines.
    Lazy binding re-reads sys.stderr on each write so the latest redirection
    takes effect."""

    def write(self, data: str) -> int:
        return sys.stderr.write(data)

    def flush(self) -> None:
        sys.stderr.flush()


def configure_logging(
    level: int = logging.INFO,
    *,
    json_output: bool = True,
    stream: Any = None,
    cache: bool = True,
) -> None:
    """Configure structlog.

    `stream` is the file object rendered lines are written to; defaults to
    sys.stdout for production (where the host captures stdout) and is set by
    the CLI to a LazyStderr() so the `crucible run --stream json` event channel
    on stdout stays clean.

    `cache` toggles structlog's logger-on-first-use cache. Tests and the CLI's
    repeated configure_logging calls (per-subcommand) disable the cache so the
    second call's processors actually take effect; production keeps it on for
    speed.
    """
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(
            file=stream if stream is not None else sys.stdout
        ),
        cache_logger_on_first_use=cache,
    )


def get_logger(name: str, **initial: Any) -> structlog.stdlib.BoundLogger:
    log: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    if initial:
        return log.bind(**initial)
    return log
