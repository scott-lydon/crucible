"""Declarative base plus the audit columns the constitution mandates on every
work-bearing row (constitution.md section 4, plan.md section 7).

``AuditMixin`` is applied to every table that represents work done by a pillar, so
that ``created_at``, ``pillar``, ``dollars_spent``, ``seed``, ``audit_trace`` and
``parent_action_id`` are present uniformly and the dashboard can render them without
special-casing."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import TIMESTAMP, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AuditMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    pillar: Mapped[str] = mapped_column(String(20), nullable=False)
    dollars_spent: Mapped[float] = mapped_column(
        Numeric(12, 6, asdecimal=False), nullable=False, default=0.0
    )
    seed: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    audit_trace: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    parent_action_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
