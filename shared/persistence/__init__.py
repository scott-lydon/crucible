"""Persistence layer: engine, session, base, ORM models.

No raw SQL lives outside this package (coding-practices.md section 1).
"""

from __future__ import annotations

from .base import Base
from .engine import (
    async_database_url,
    get_engine,
    get_session,
    get_sessionmaker,
    ping,
    reset_engine_for_tests,
    use_database,
)
from .spec_resolver import SpecNotFoundError, SpecResolver

__all__ = [
    "Base",
    "SpecNotFoundError",
    "SpecResolver",
    "async_database_url",
    "get_engine",
    "get_session",
    "get_sessionmaker",
    "ping",
    "reset_engine_for_tests",
    "use_database",
]
