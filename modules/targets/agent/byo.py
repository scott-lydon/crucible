"""Bring-your-own-agent builders (cr-a3). Two BYO paths:

* model + system prompt — the user picks an OpenRouter model and pastes a system
  prompt; we wrap it in an ``AgentTarget`` over the real LLM transport.
* HTTP endpoint (advanced) — the user's agent already runs behind a URL; we wrap it in
  an ``HttpAgentTarget`` and treat it as a black box.

Validation fails loud on an empty model/prompt/endpoint rather than launching a run
that can only error (constitution.md section 8)."""

from __future__ import annotations

from modules.targets.agent.http_target import HttpAgentTarget, HttpEndpointConfig
from modules.targets.agent.target import AgentTarget
from shared.llm import make_llm
from shared.llm.client import LLMClient
from shared.types.agent import AgentConfig

# A curated shortlist the Run Launcher offers as a dropdown. The user may still type any
# OpenRouter model id; these are the ones we test against and recommend.
SUPPORTED_MODELS: tuple[str, ...] = (
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-opus-4.8",
    "anthropic/claude-haiku-4.5",
    "openai/gpt-4o-mini",
    "google/gemini-2.5-flash",
    "meta-llama/llama-3.1-8b-instruct",
)


def validate_agent_config(config: AgentConfig) -> None:
    """Reject a BYO model+prompt config that cannot launch a meaningful run."""
    if not config.model.strip():
        raise ValueError("BYO agent: model id is required")
    if not config.system_prompt.strip():
        raise ValueError("BYO agent: a system prompt is required")
    if not config.name.strip():
        raise ValueError("BYO agent: a name is required")


def build_agent_target(config: AgentConfig, *, llm: LLMClient | None = None) -> AgentTarget:
    """Construct an AgentTarget from a BYO model+prompt config. ``llm`` is injected in
    tests; in production it is the real OpenRouter client for ``config.model``."""
    validate_agent_config(config)
    client = llm if llm is not None else make_llm(config.model)
    return AgentTarget(client, config)


def validate_http_endpoint(config: HttpEndpointConfig) -> None:
    if not config.endpoint.strip():
        raise ValueError("BYO HTTP agent: an endpoint URL is required")
    if not config.endpoint.startswith(("http://", "https://")):
        raise ValueError(f"BYO HTTP agent: endpoint must be http(s), got {config.endpoint!r}")
    if not config.name.strip():
        raise ValueError("BYO HTTP agent: a name is required")


def build_http_agent_target(config: HttpEndpointConfig) -> HttpAgentTarget:
    validate_http_endpoint(config)
    return HttpAgentTarget(config)
