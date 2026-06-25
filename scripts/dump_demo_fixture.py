"""Dump the local real-LLM demo data to a portable JSON fixture.

Run locally (reads DATABASE_URL = local Postgres). The companion seed loader
(scripts/seed_demo.py) loads it INTO the deploy DB on container start, so the
deployed app renders the same real numbers the local instance shows. The data is
a real captured snapshot of real-LLM runs (disclosed as a snapshot, not a fresh
live run).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import Any

for line in open(".env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)
sys.path.insert(0, os.getcwd())

# Imports below run after the .env load and sys.path insertion above, so they
# are intentionally not at the top of the module.
from sqlalchemy import select  # noqa: E402

from shared.persistence.base import Base  # noqa: E402
from shared.persistence.engine import get_engine, use_database  # noqa: E402


def enc(v: Any) -> Any:
    if isinstance(v, datetime):
        return {"__dt__": v.isoformat()}
    if isinstance(v, date):
        return {"__date__": v.isoformat()}
    if isinstance(v, Decimal):
        return {"__dec__": str(v)}
    return v  # str/int/float/bool/None/dict/list (JSONB) are JSON-native


async def main() -> None:
    use_database(os.environ["DATABASE_URL"])
    eng = get_engine()
    tables: dict[str, list[dict[str, Any]]] = {}
    async with eng.begin() as conn:
        for table in Base.metadata.sorted_tables:
            rows = (await conn.execute(select(table))).mappings().all()
            cols = [c.name for c in table.columns]
            tables[table.name] = [
                {c: enc(r[c]) for c in cols} for r in rows
            ]
    out: dict[str, Any] = {"__marker_table__": "runs", "tables": tables}
    total = sum(len(v) for v in tables.values())
    json.dump(out, open("seed/crucible_demo.json", "w"), indent=0)
    print("wrote seed/crucible_demo.json  tables:",
          {k: len(v) for k, v in tables.items() if v}, " total rows:", total)


asyncio.run(main())
