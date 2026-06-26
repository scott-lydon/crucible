"""Capture the current local Postgres state into seed/crucible_demo.json.

Run after a real-LLM session populates the database:

    DATABASE_URL=... python scripts/capture_demo.py

The output uses the same tagged-value encoding that seed_demo.py expects
(__dt__, __date__, __dec__) so the loader round-trips cleanly. The marker
table defaults to "runs" (matching seed_demo.py's idempotency check).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import Any

# Ensure the repo root is importable.
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _HERE)


def _encode(v: Any) -> Any:
    """Mirror the tag decoders in seed_demo.py so the capture round-trips."""
    if isinstance(v, datetime):
        return {"__dt__": v.isoformat()}
    if isinstance(v, date):
        return {"__date__": v.isoformat()}
    if isinstance(v, Decimal):
        return {"__dec__": str(v)}
    if isinstance(v, dict):
        return {k: _encode(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_encode(item) for item in v]
    return v


async def _capture() -> None:
    from sqlalchemy import select, text

    from shared.persistence.base import Base
    from shared.persistence.db import get_engine

    # Force the ORM models to register on Base.metadata.
    import shared.persistence.models  # noqa: F401

    eng = get_engine()
    sorted_tables = list(Base.metadata.sorted_tables)

    tables_data: dict[str, list[dict[str, Any]]] = {}
    total = 0

    async with eng.begin() as conn:
        for table in sorted_tables:
            result = await conn.execute(select(table))
            rows = [dict(row._mapping) for row in result.fetchall()]
            encoded = [{k: _encode(v) for k, v in row.items()} for row in rows]
            tables_data[table.name] = encoded
            total += len(encoded)
            print(f"  {table.name}: {len(encoded)} rows")

    fixture = {
        "__marker_table__": "runs",
        "__captured_at__": datetime.now().isoformat(),
        "__table_count__": len(sorted_tables),
        "__row_count__": total,
        "tables": tables_data,
    }

    out_path = os.path.join(_HERE, "seed", "crucible_demo.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(fixture, fh, indent=2, default=str)
    print(f"\nCaptured {total} rows across {len(sorted_tables)} tables → {out_path}")


def main() -> None:
    asyncio.run(_capture())


if __name__ == "__main__":
    main()
