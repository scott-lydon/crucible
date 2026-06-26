"""AgentTarget: the Shape-2 adapter. It wraps one vendor LLM behind a system
prompt (an ``AgentConfig``) and exposes the platform's Target port. ``submit`` is one
chat turn: the producer sees ONLY the adversarial input the red crafts (never the
sealed spec), the system prompt steers it, and the text it returns is the output the
oracle ensemble grades for silent failure.

Mock-first: a ScriptedLLM is injected in tests/CI (free, deterministic); real Sonnet
via OpenRouter is wired for the demo. Every call's cost flows onto the ProducerResult
so the run's dollars are honest (constitution.md section 4)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from shared.llm.client import LLMClient
from shared.types.agent import AgentConfig
from shared.types.core import AuditTrace
from shared.types.enums import Pillar, Shape
from shared.types.results import HealthStatus, ProducerResult

AGENT_KIND = "agent"

# The keys an adversarial payload may carry the user-visible turn under. The red
# crafts natural-language inputs; the loop and oracles only ever hand the producer
# this `payload`, so the input is whatever the red put here.
_INPUT_KEYS = ("input", "prompt", "message", "text", "query")


class AgentTarget:
    """A user-supplied agent: a model + system prompt the platform stress-tests."""

    shape: Shape = Shape.shape2_agent

    def __init__(self, llm: LLMClient, config: AgentConfig, *, kind: str = AGENT_KIND) -> None:
        self._llm = llm
        self._config = config
        self.kind = kind

    @property
    def config(self) -> AgentConfig:
        return self._config

    @staticmethod
    def _extract_input(payload: Mapping[str, Any]) -> str:
        """The user turn the red wants the agent to answer. Falls back to the whole
        payload as JSON so a structured attack still reaches the agent verbatim."""
        for key in _INPUT_KEYS:
            value = payload.get(key)
            if value is not None:
                return str(value)
        return json.dumps(dict(payload), sort_keys=True)

    async def submit(self, payload: Mapping[str, Any]) -> ProducerResult:
        user_input = self._extract_input(payload)
        max_tokens = int(self._config.params.get("max_tokens", 600))
        result = await self._llm.complete(
            self._config.system_prompt, user_input, max_tokens=max_tokens
        )
        return ProducerResult(
            output={"response": result.text, "model": result.model},
            audit=AuditTrace(
                pillar=Pillar.targets,
                summary=(
                    f"agent '{self._config.name}' v{self._config.version} "
                    f"({result.model}) -> {len(result.text)} chars"
                ),
                detail={
                    "agent": self._config.name,
                    "version": self._config.version,
                    "model": result.model,
                    "system_prompt_chars": len(self._config.system_prompt),
                    "input_preview": user_input[:300],
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                },
            ),
            dollars=result.dollars,
        )

    async def health(self) -> HealthStatus:
        # No live call: a real-LLM roundtrip would bill the operator on every /health
        # poll. Report readiness from the wired client + config instead.
        if not self._llm.available:
            return HealthStatus(
                status="amber",
                detail={"target": self.kind, "agent": self._config.name},
                error="LLM provider not configured (set OPENROUTER_API_KEY for real runs)",
            )
        return HealthStatus(
            status="green",
            detail={
                "target": self.kind,
                "agent": self._config.name,
                "version": self._config.version,
                "model": self._config.model,
                "system_prompt_chars": len(self._config.system_prompt),
            },
        )
