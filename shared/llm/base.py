"""LLM provider port.

The seam through which Crucible's red agent, blue agent, and LLM-judge oracle
call an LLM. A ``Protocol`` port with swappable adapters keeps the design
vendor-agnostic: the production Anthropic adapter and a deterministic mock both
satisfy ``LLMProvider``. (Constitution §1 mandates Anthropic only — do not add a
second production vendor — but the port stays vendor-agnostic by design.)
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """A single completion result, with token accounting and cost."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    dollars: float
    raw: Mapping[str, object] = field(default_factory=dict)


class LLMProvider(Protocol):
    """Port for synchronous single-turn completions."""

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        json_schema: Mapping[str, object] | None = None,
    ) -> LLMResponse: ...
