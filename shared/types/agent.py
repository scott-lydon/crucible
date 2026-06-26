"""Agent value objects. An ``AgentConfig`` is the in-memory description of a
Shape-2 target (an agent product on a vendor LLM, VOCABULARY.md Shape 2): the model
to call, the system prompt that defines its behaviour, and tuning params. It is the
unit the Blue pillar versions when it hardens an agent — it rewrites the system
prompt and emits a new ``AgentConfig`` version (the vendor model is never retrained,
plan.md section 5). Kept in shared/types so targets, red, blue and persistence all
speak it without importing each other (constitution.md section 2)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentConfig:
    """One configuration of a Shape-2 agent target.

    ``name`` identifies the agent across versions; ``version`` increments each time
    Blue hardens it. ``system_prompt`` is the editable guardrail surface; the vendor
    ``model`` behind it is fixed (you can't retrain a rented model)."""

    name: str
    model: str
    system_prompt: str
    description: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)
    version: int = 1

    def revised(self, system_prompt: str, *, version: int | None = None) -> AgentConfig:
        """A new version of this agent with a rewritten system prompt — the Blue
        pillar's hardening output. Everything else (model, params) is carried over."""
        return AgentConfig(
            name=self.name,
            model=self.model,
            system_prompt=system_prompt,
            description=self.description,
            params=dict(self.params),
            version=version if version is not None else self.version + 1,
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable form for the ``agent_configs`` table and audit traces."""
        return {
            "name": self.name,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "description": self.description,
            "params": dict(self.params),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> AgentConfig:
        return cls(
            name=str(raw["name"]),
            model=str(raw["model"]),
            system_prompt=str(raw["system_prompt"]),
            description=str(raw.get("description", "")),
            params=dict(raw.get("params", {})),
            version=int(raw.get("version", 1)),
        )
