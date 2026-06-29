"""File-local persistence for headless runs: a SQLite database inside the run dir.

The web deployment uses Postgres; the CLI does not require it. Per run we point the
existing persistence layer (shared/persistence) at a SQLite file under the run dir, so
the SAME models, resolver, and loop persistence code run unchanged. The only adaptation
is a DDL-compile hook so the Postgres ``JSONB`` columns emit ``JSON`` on SQLite (JSON
value serialization is inherited from the generic JSON type, so dict columns round-trip).

This keeps Postgres optional, not required (Slice 0), without forking the models."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

_hook_installed = False


def _install_jsonb_sqlite_hook() -> None:
    global _hook_installed
    if _hook_installed:
        return

    @compiles(JSONB, "sqlite")
    def _compile_jsonb_as_json(type_: object, compiler: object, **kw: object) -> str:
        return "JSON"

    _hook_installed = True


async def init_local_db(db_path: Path) -> str:
    """Point persistence at ``db_path`` (SQLite) and create the schema. Returns the URL.

    Sets DATABASE_URL, disposes any existing engine so the new URL takes effect, then
    creates every table from the declarative metadata (no Alembic needed for the
    throwaway per-run file)."""
    _install_jsonb_sqlite_hook()
    url = f"sqlite+aiosqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url

    # Import after setting the env so a fresh engine binds to the SQLite URL.
    from shared.persistence import models  # noqa: F401  (registers tables on Base)
    from shared.persistence.base import Base
    from shared.persistence.db import get_engine, reset_engine

    await reset_engine()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return url
