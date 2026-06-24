"""structlog configuration.

JSON logs to stdout, captured by Render in production. Each log line carries
whatever context the caller binds (run_id, pillar, subcomponent, seed), per
ARCHITECTURE.md section 10. Configuration is idempotent so importing modules
can call it freely.
"""

from __future__ import annotations

from typing import Any

import structlog


def configure_logging() -> None:
    """Configure structlog for JSON stdout output. Safe to call repeatedly."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        cache_logger_on_first_use=True,
    )


def get_logger(name: str, **initial_context: Any) -> structlog.stdlib.BoundLogger:
    """Return a bound logger pre-seeded with the given context fields."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    if initial_context:
        return logger.bind(**initial_context)
    return logger
