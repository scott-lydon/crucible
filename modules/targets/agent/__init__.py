"""The generic AGENT target (Shape 2): bring any AI agent — a vendor model plus a
system prompt — and the platform red-teams it. The fraud LightGBM was the bounded
case; agents are natural language, so the AI attacker/defender operate directly
(plan.md sections 3 and 5)."""

from __future__ import annotations

from modules.targets.agent.byo import (
    SUPPORTED_MODELS,
    build_agent_target,
    build_http_agent_target,
    validate_agent_config,
    validate_http_endpoint,
)
from modules.targets.agent.demos import DEMO_AGENTS, DEMO_SPECS, demo_agent, demo_spec
from modules.targets.agent.http_target import (
    HTTP_AGENT_KIND,
    HttpAgentTarget,
    HttpEndpointConfig,
)
from modules.targets.agent.target import AGENT_KIND, AgentTarget

__all__ = [
    "AGENT_KIND",
    "DEMO_AGENTS",
    "DEMO_SPECS",
    "HTTP_AGENT_KIND",
    "SUPPORTED_MODELS",
    "AgentTarget",
    "HttpAgentTarget",
    "HttpEndpointConfig",
    "build_agent_target",
    "build_http_agent_target",
    "demo_agent",
    "demo_spec",
    "validate_agent_config",
    "validate_http_endpoint",
]
