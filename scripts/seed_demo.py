"""Seed the deploy database from a captured real-LLM snapshot, on container start.

Why this exists: Render runs MOCK_LLM=true (no `claude` CLI), so runs launched on
the deploy use the mock judge and produce degenerate metrics (0% catch). The real,
meaningful data lives in the local real-LLM Postgres. External clients cannot write
to the Render Postgres (it only accepts connections from inside Render's network),
so this loader runs INSIDE the container at boot, where the DB is reachable, and
loads seed/crucible_demo.json — a real captured snapshot of real-LLM runs.

DISCLOSURE: this is a captured snapshot, not a fresh live run. The narration / UI
must say so. It is real data (real Claude judged it), just persisted from a prior
real-LLM session into the deploy DB.

Safety:
- Gated by env CRUCIBLE_SEED_DEMO == "true". Unset/false -> no-op. This keeps the
  destructive table reset behind an explicit operator flag.
- Idempotent: if the marker run from the fixture already exists, skip. So repeated
  deploys after the first seed are no-ops.
- Never crashes the boot: any error is logged and the process exits 0 so the app
  still starts (alembic upgrade head ran before this in the Dockerfile CMD).
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal

_TAG_DECODERS = {
    "__dt__": datetime.fromisoformat,
    "__date__": date.fromisoformat,
    "__dec__": Decimal,
}


def _dec(v):
    if isinstance(v, dict) and len(v) == 1:
        (k, val), = v.items()
        if k in _TAG_DECODERS:
            return _TAG_DECODERS[k](val)
    return v


async def _seed() -> None:
    if os.environ.get("CRUCIBLE_SEED_DEMO", "").lower() != "true":
        print("[seed_demo] CRUCIBLE_SEED_DEMO not 'true'; skipping.")
        return

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, here)
    fixture_path = os.path.join(here, "seed", "crucible_demo.json")
    if not os.path.exists(fixture_path):
        print(f"[seed_demo] fixture missing at {fixture_path}; skipping.")
        return
    fixture = json.load(open(fixture_path))
    tables_data = fixture["tables"]

    from sqlalchemy import delete, func, select
    from shared.persistence.base import Base
    from shared.persistence.engine import get_engine

    eng = get_engine()
    sorted_tables = list(Base.metadata.sorted_tables)
    by_name = {t.name: t for t in sorted_tables}

    marker_table = by_name.get(fixture.get("__marker_table__", "runs"))
    marker_rows = tables_data.get(marker_table.name, []) if marker_table is not None else []
    marker_ids = [r.get("id") for r in marker_rows if r.get("id") is not None]

    async with eng.begin() as conn:
        if marker_ids and marker_table is not None:
            existing = (
                await conn.execute(
                    select(func.count()).select_from(marker_table).where(
                        marker_table.c.id.in_(marker_ids)
                    )
                )
            ).scalar()
            if existing and existing >= len(marker_ids):
                print(f"[seed_demo] snapshot already present ({existing} marker rows); skipping.")
                return

        # Reset the (mock) data tables in reverse FK order, then load the snapshot.
        for table in reversed(sorted_tables):
            await conn.execute(delete(table))
        loaded = 0
        for table in sorted_tables:
            rows = tables_data.get(table.name) or []
            if not rows:
                continue
            cols = {c.name for c in table.columns}
            decoded = [
                {k: _dec(v) for k, v in row.items() if k in cols} for row in rows
            ]
            await conn.execute(table.insert(), decoded)
            loaded += len(decoded)
        print(f"[seed_demo] seeded {loaded} rows from snapshot into the deploy DB.")


def main() -> None:
    try:
        asyncio.run(_seed())
    except Exception as exc:  # never break container boot
        print(f"[seed_demo] non-fatal error, continuing boot: {exc!r}")


if __name__ == "__main__":
    main()
