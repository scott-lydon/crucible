"""LLM transport. ``make_llm`` returns the real provider for a given model; tests
inject ``ScriptedLLM`` directly through wiring instead."""

from __future__ import annotations

from shared.config import load_settings
from shared.llm.client import (
    LLMClient,
    LLMResult,
    OpenRouterClient,
    ScriptedLLM,
    record_llm_call,
)

__all__ = [
    "LLMClient",
    "LLMResult",
    "OpenRouterClient",
    "ScriptedLLM",
    "make_llm",
    "record_llm_call",
]


def make_llm(model: str) -> LLMClient:
    """Real LLM client for ``model``. Fails loud if no provider is configured —
    never silently falls back to a stub (constitution.md section 8)."""
    settings = load_settings()
    if settings.openrouter_api_key:
        return OpenRouterClient(model=model, api_key=settings.openrouter_api_key)
    raise RuntimeError(
        "No LLM provider configured: set OPENROUTER_API_KEY (or place the key at "
        "~/.config/crucible/openrouter.key)."
    )
