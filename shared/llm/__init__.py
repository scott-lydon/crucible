"""LLM transport. ``make_llm`` returns the real provider for a given model; tests
inject ``ScriptedLLM`` directly through wiring instead."""

from __future__ import annotations

from shared.config import load_settings
from shared.llm.client import (
    AnthropicClient,
    LLMClient,
    LLMResult,
    OpenRouterClient,
    ScriptedLLM,
    record_llm_call,
)
from shared.llm.recording import (
    LLMCallRecord,
    RecordingLLM,
    drain_records,
    record_into,
)

__all__ = [
    "AnthropicClient",
    "LLMCallRecord",
    "LLMClient",
    "LLMResult",
    "OpenRouterClient",
    "RecordingLLM",
    "ScriptedLLM",
    "drain_records",
    "make_llm",
    "record_into",
    "record_llm_call",
]


def make_llm(model: str) -> LLMClient:
    """Real LLM client for ``model``. Prefers Anthropic SDK when ANTHROPIC_API_KEY
    is set; falls back to OpenRouter. Fails loud if neither is configured (never
    silently falls back to a stub, constitution.md section 8)."""
    settings = load_settings()
    if settings.anthropic_api_key:
        return AnthropicClient(model=model, api_key=settings.anthropic_api_key)
    if settings.openrouter_api_key:
        return OpenRouterClient(model=model, api_key=settings.openrouter_api_key)
    raise RuntimeError(
        "No LLM provider configured: set ANTHROPIC_API_KEY or OPENROUTER_API_KEY "
        "(or place the OpenRouter key at ~/.config/crucible/openrouter.key)."
    )
