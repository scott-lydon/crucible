"""Process configuration, parsed once from the environment.

Secrets (Anthropic key, Postgres URL) come from the environment or a
.gitignored .env, never from the repo (ARCHITECTURE.md section 9). The
database URL defaults to the local docker-compose Postgres so a fresh
checkout runs the test suite with one `docker compose up`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view of the environment. Unknown variables are ignored."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://crucible:crucible@localhost:5432/crucible"
    anthropic_api_key: str | None = None
    # Verifier recall on the white-box self-test below this halts certification (US-13).
    halt_recall_threshold: float = 0.7
    # When true the Anthropic client returns fixture responses; surfaced in the
    # run header so a mock run can never be mistaken for a real one (US-15).
    mock_llm: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
