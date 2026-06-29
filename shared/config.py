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
    # Explicit operator override for the differential reference model. None => Crucible
    # auto-picks a DIFFERENT family than the producer (shared/model_family.py), gracefully
    # falling back when the family is unknown. Set CRUCIBLE_DIFFERENTIAL_MODEL to force one.
    differential_model: str | None
    # The held-out is the GROUND-TRUTH anchor (trust, recall AND co-evolution safe-rate all read
    # it, and nothing else computes ground truth), so ACCURACY matters most. It runs on the
    # strongest available non-Anthropic model (GPT-5.5) — accurate AND independent of the Opus
    # judge. Two families (Anthropic judge + OpenAI held-out/differential) is enough corroboration
    # for the demo; a weaker "third vendor" on the answer key would just understate failures.
    # Override with CRUCIBLE_HELDOUT_MODEL.
    held_out_model: str
    halt_recall_threshold: float
    global_budget_dollars: float  # hard ceiling on total real-LLM spend across all runs


def _read_key_file(path: str) -> str | None:
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def load_settings() -> Settings:
    opus_model = os.environ.get("CRUCIBLE_OPUS_MODEL", "anthropic/claude-opus-4.8")
    return Settings(
        database_url=os.environ.get("DATABASE_URL", _DEFAULT_DB),
        openrouter_api_key=(
            os.environ.get("OPENROUTER_API_KEY")
            or _read_key_file("~/.config/crucible/openrouter.key")
        ),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        sonnet_model=os.environ.get("CRUCIBLE_SONNET_MODEL", "anthropic/claude-sonnet-4.6"),
        opus_model=opus_model,
        differential_model=os.environ.get("CRUCIBLE_DIFFERENTIAL_MODEL"),
        held_out_model=os.environ.get("CRUCIBLE_HELDOUT_MODEL", "openai/gpt-5.5"),
        halt_recall_threshold=float(os.environ.get("CRUCIBLE_HALT_RECALL", "0.7")),
        global_budget_dollars=float(os.environ.get("CRUCIBLE_GLOBAL_BUDGET", "25.0")),
    )
