"""Declarative base shared by every ORM model.

One base means one metadata object, which Alembic autogenerate and the test
schema builder both read from a single point of truth.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all Crucible ORM models."""
