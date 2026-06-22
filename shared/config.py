"""Process configuration, read once from the environment. Secrets never live in
the repo (constitution.md section 4); local development reads from a gitignored
``.env`` exported into the shell, or from the defaults below for the dev Postgres."""

from __future__ import annotations

import os
from dataclasses import dataclass

# The dedicated dev Postgres container (risk spike cr-r4): host ports 5432-5434 are
# taken by other apps on this VPS, so crucible-pg publishes on 55432.
_DEFAULT_DB = "postgresql+asyncpg://crucible:crucible@127.0.0.1:55432/crucible"


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    openrouter_api_key: str | None
    anthropic_api_key: str | None
    sonnet_model: str   # inner red/blue loops (constitution.md section 1)
    opus_model: str     # judge oracle + white-box self-test pass
    halt_recall_threshold: float


def _read_key_file(path: str) -> str | None:
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def load_settings() -> Settings:
    return Settings(
        database_url=os.environ.get("DATABASE_URL", _DEFAULT_DB),
        openrouter_api_key=(
            os.environ.get("OPENROUTER_API_KEY")
            or _read_key_file("~/.config/crucible/openrouter.key")
        ),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        sonnet_model=os.environ.get("CRUCIBLE_SONNET_MODEL", "anthropic/claude-sonnet-4.6"),
        opus_model=os.environ.get("CRUCIBLE_OPUS_MODEL", "anthropic/claude-opus-4.8"),
        halt_recall_threshold=float(os.environ.get("CRUCIBLE_HALT_RECALL", "0.7")),
    )
