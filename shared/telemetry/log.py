"""Structured logging. Every log line carries run_id / pillar / subcomponent / seed
where available (plan.md section 10). JSON to stdout in production, captured by the
host."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(level: int = logging.INFO, *, json_output: bool = True) -> None:
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
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str, **initial: Any) -> structlog.stdlib.BoundLogger:
    log: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    if initial:
        return log.bind(**initial)
    return log
