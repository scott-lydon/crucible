"""The generic AGENT target (Shape 2): bring any AI agent — a vendor model plus a
system prompt — and the platform red-teams it. The fraud LightGBM was the bounded
case; agents are natural language, so the AI attacker/defender operate directly
(plan.md sections 3 and 5)."""

from __future__ import annotations

from modules.targets.agent.demos import DEMO_AGENTS, DEMO_SPECS, demo_agent, demo_spec
from modules.targets.agent.target import AGENT_KIND, AgentTarget

__all__ = [
    "AGENT_KIND",
    "DEMO_AGENTS",
    "DEMO_SPECS",
    "AgentTarget",
    "demo_agent",
    "demo_spec",
]
