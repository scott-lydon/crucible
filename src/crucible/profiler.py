"""Profiler — turns whatever the adapter exposes into a target model the attacker
and oracles consume. Grey-box: reads system prompt, tools, guardrails, declared
secrets. Black-box: minimal profile, suggest-only downstream."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .adapter import TargetAdapter

_SECRET_RE = re.compile(r"\b(CANARY-[A-Za-z0-9\-]+|sk-[A-Za-z0-9]{8,}|[A-Za-z0-9]{24,})\b")


@dataclass
class TargetProfile:
    access: str = "black-box"          # black-box | grey-box
    system_prompt: str | None = None
    tools: list[dict] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)
    refund_limit: float = 100.0


def profile_target(target: TargetAdapter) -> TargetProfile:
    cfg = None
    try:
        cfg = target.get_config()
    except Exception:  # noqa: BLE001
        cfg = None
    if not cfg:
        return TargetProfile(access="black-box")

    secrets = list(cfg.get("secrets", []))
    sysprompt = cfg.get("system_prompt")
    if sysprompt:
        # discover secret-looking tokens in the visible prompt (grey-box advantage)
        for m in _SECRET_RE.findall(sysprompt):
            if m not in secrets:
                secrets.append(m)
    return TargetProfile(
        access="grey-box",
        system_prompt=sysprompt,
        tools=cfg.get("tools", []),
        guardrails=list(cfg.get("guardrails", [])),
        secrets=secrets,
        refund_limit=float(cfg.get("tool_limits", {}).get("refund_max") or 100.0),
    )
