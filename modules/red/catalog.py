"""Strategy catalog: the red pillar's institutional memory (US-6).

Every successful evasion is recorded so the platform remembers tactics across
runs and the demo shows the catalog growing. Persistence is twofold per the
architecture: a Postgres table the dashboard reads (one row per tactic per
target type, with a reuse count and running dollar total), and an append-only
JSONL log that captures every individual discovery for export and audit.

The catalog never trusts a single side as ground truth and stores no secrets:
it records the tactic name, the payload fragment, and the discovery audit, all
of which are the attacker's own output.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.persistence.models import StrategyCatalogEntry
from shared.types import Attack, TargetType


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """One catalog row, shaped for the /catalog table (US-6)."""

    tactic: str
    target_type: str
    first_run_id: str
    reuse_count: int
    avg_dollars_to_succeed: float
    prompt_fragment: str
    discovery_audit: dict[str, Any]

    def as_json(self) -> dict[str, Any]:
        return {
            "tactic": self.tactic,
            "target_type": self.target_type,
            "first_run_id": self.first_run_id,
            "reuse_count": self.reuse_count,
            "avg_dollars_to_succeed": self.avg_dollars_to_succeed,
            "prompt_fragment": self.prompt_fragment,
            "discovery_audit": self.discovery_audit,
        }


@dataclass(frozen=True, slots=True)
class StrategyCatalog:
    """Reads and writes the strategy catalog over one database session."""

    session: AsyncSession
    jsonl_path: Path

    async def record_success(self, attack: Attack, target_type: TargetType) -> None:
        """Record one successful evasion, upserting by (tactic, target_type).

        First discovery inserts a row; a rediscovery increments the reuse count
        and adds to the dollar total, so the average dollars-to-succeed stays
        the real running mean rather than a guess. The caller owns the
        transaction (this adds and flushes, the loop or route commits); the
        JSONL line is appended immediately as an append-only discovery log.
        """
        dollars = attack.dollars_spent.dollars
        existing = (
            await self.session.execute(
                select(StrategyCatalogEntry).where(
                    StrategyCatalogEntry.tactic == attack.tactic,
                    StrategyCatalogEntry.target_type == target_type.value,
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            self.session.add(
                StrategyCatalogEntry(
                    id=uuid.uuid4().hex,
                    tactic=attack.tactic,
                    target_type=target_type.value,
                    first_run_id=attack.run_id.value,
                    reuse_count=1,
                    total_dollars=dollars,
                    prompt_fragment=json.dumps(attack.payload, sort_keys=True),
                    discovery_audit=attack.audit.as_json(),
                )
            )
        else:
            existing.reuse_count += 1
            existing.total_dollars += dollars
        await self.session.flush()
        self._append_jsonl(attack, target_type)

    async def entries(self, target_type: TargetType | None = None) -> list[CatalogEntry]:
        """Return catalog rows, most-reused first, optionally filtered by target."""
        query = select(StrategyCatalogEntry).order_by(
            StrategyCatalogEntry.reuse_count.desc(), StrategyCatalogEntry.created_at.desc()
        )
        if target_type is not None:
            query = query.where(StrategyCatalogEntry.target_type == target_type.value)
        rows = (await self.session.execute(query)).scalars().all()
        return [self._to_entry(row) for row in rows]

    @staticmethod
    def _to_entry(row: StrategyCatalogEntry) -> CatalogEntry:
        count = row.reuse_count if row.reuse_count > 0 else 1
        avg = float(row.total_dollars / Decimal(count))
        return CatalogEntry(
            tactic=row.tactic,
            target_type=row.target_type,
            first_run_id=row.first_run_id,
            reuse_count=row.reuse_count,
            avg_dollars_to_succeed=avg,
            prompt_fragment=row.prompt_fragment,
            discovery_audit=row.discovery_audit,
        )

    def _append_jsonl(self, attack: Attack, target_type: TargetType) -> None:
        """Append one discovery to the append-only JSONL log."""
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "recorded_at": datetime.now(UTC).isoformat(),
                "tactic": attack.tactic,
                "target_type": target_type.value,
                "run_id": attack.run_id.value,
                "attack_id": attack.attack_id.value,
                "payload": attack.payload,
                "dollars": str(attack.dollars_spent.dollars),
            },
            sort_keys=True,
        )
        with self.jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
