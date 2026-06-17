"""The target adapter — the progressive contract between Crucible and the agent.

Levels of access:
  L0 black-box : send(message) -> Response only.
  L1 grey-box  : + get_config() exposes system_prompt / tools / guardrails.
  L2 white-box : + repo access (future).

`clone_with_config(patch)` lets the fix engine build a sandboxed, modified copy
of the target to re-evaluate a candidate fix WITHOUT touching anything live. A
black-box target cannot be cloned, so the fix engine degrades to suggest-only.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Callable, Protocol, runtime_checkable

from .models import Response, ToolCall


@runtime_checkable
class TargetAdapter(Protocol):
    def send(self, message: str) -> Response: ...

    def get_config(self) -> dict[str, Any] | None:
        """Grey-box AI-layer config (system_prompt, tools, guardrails) or None."""
        ...

    def clone_with_config(self, patch: dict[str, Any]) -> "TargetAdapter | None":
        """Return a sandboxed copy with the AI-layer config patch applied, or None."""
        ...


class CallableAdapter:
    """Wrap any python callable `fn(message) -> str | Response`. Black-box by default."""

    def __init__(self, fn: Callable[[str], Any]):
        self._fn = fn

    def send(self, message: str) -> Response:
        out = self._fn(message)
        if isinstance(out, Response):
            return out
        return Response(text=str(out))

    def get_config(self) -> dict[str, Any] | None:
        return None

    def clone_with_config(self, patch: dict[str, Any]) -> "TargetAdapter | None":
        return None


class HTTPAdapter:
    """POST {"message": ...} to an endpoint expecting {"text": ..., "tool_calls": [...]}.

    Best-effort, stdlib-only. Black-box (no config/clone).
    """

    def __init__(self, url: str, timeout: float = 30.0):
        self.url = url
        self.timeout = timeout

    def send(self, message: str) -> Response:
        data = json.dumps({"message": message}).encode()
        req = urllib.request.Request(
            self.url, data=data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
            body = json.loads(resp.read().decode())
        calls = [ToolCall(name=c.get("name", ""), args=c.get("args", {}))
                 for c in body.get("tool_calls", [])]
        return Response(text=body.get("text", ""), tool_calls=calls)

    def get_config(self) -> dict[str, Any] | None:
        return None

    def clone_with_config(self, patch: dict[str, Any]) -> "TargetAdapter | None":
        return None
