"""LLM access layer over the local Claude Max CLI.

Cross-cutting infrastructure used by the red, blue, and oracle pillars, so it
lives in `shared/` per coding-practices.md section 2.
"""

from __future__ import annotations

from .client import (
    ClaudeCliClient,
    LlmClient,
    ScriptedLlmClient,
    get_llm_client,
    parse_cli_json,
)
from .errors import LlmCallError
from .models import LlmModel, LlmResult

__all__ = [
    "ClaudeCliClient",
    "LlmCallError",
    "LlmClient",
    "LlmModel",
    "LlmResult",
    "ScriptedLlmClient",
    "get_llm_client",
    "parse_cli_json",
]
