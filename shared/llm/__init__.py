"""LLM access layer over the local Claude Max CLI.

Cross-cutting infrastructure used by the red, blue, and oracle pillars, so it
lives in `shared/` per coding-practices.md section 2. The deploy-time fallback
to the Anthropic Messages API (no local CLI) lives alongside it here.
"""

from __future__ import annotations

from .active_key import (
    ActiveKey,
    KeySource,
    clear_active_key,
    get_active_key,
    key_hint,
    set_active_key,
)
from .api_client import AnthropicApiClient, parse_api_json
from .client import (
    ClaudeCliClient,
    LlmClient,
    ProviderMode,
    ScriptedLlmClient,
    get_llm_client,
    parse_cli_json,
    resolve_provider_mode,
)
from .errors import AnthropicApiError, LlmCallError, NoLlmProviderError
from .models import LlmModel, LlmResult

__all__ = [
    "ActiveKey",
    "AnthropicApiClient",
    "AnthropicApiError",
    "ClaudeCliClient",
    "KeySource",
    "LlmCallError",
    "LlmClient",
    "LlmModel",
    "LlmResult",
    "NoLlmProviderError",
    "ProviderMode",
    "ScriptedLlmClient",
    "clear_active_key",
    "get_active_key",
    "get_llm_client",
    "key_hint",
    "parse_api_json",
    "parse_cli_json",
    "resolve_provider_mode",
    "set_active_key",
]
