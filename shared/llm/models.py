"""LLM model selection and result types.

Model values are the exact Anthropic model strings the proposal mandates, so a
run pins the precise version (Sonnet 4.6 on the inner loops, Opus 4.8 on the
judge and white-box pass, Haiku for the code differential's second family).
They are passed straight to the `claude` CLI `--model` flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from shared.types import Money


class LlmModel(StrEnum):
    """The Claude models Crucible calls, by exact version string."""

    SONNET = "claude-sonnet-4-6"
    OPUS = "claude-opus-4-8"
    HAIKU = "claude-haiku-4-5-20251001"


@dataclass(frozen=True, slots=True)
class LlmResult:
    """One completed LLM call, with the cost and usage the dashboard surfaces.

    `dollars` is the cost the CLI reports for the call. On the Claude Max
    subscription the spend is covered, but the figure is still the real
    metered cost of the call, so the transparency column stays honest.
    `raw` is the full CLI JSON, surfaced as the dashboard trace card.
    """

    text: str
    model: LlmModel
    dollars: Money
    tokens_in: int
    tokens_out: int
    session_id: str
    raw: dict[str, Any]
