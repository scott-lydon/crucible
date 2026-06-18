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
import os
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


def _dig(obj: Any, path: str) -> Any:
    """Navigate a dot/index path into nested JSON, e.g. 'choices.0.message.content'."""
    cur = obj
    for part in str(path).split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


class HTTPAdapter:
    """Configurable adapter for a custom agent HTTP endpoint.

    Sends ``{**body_extra, message_field: message}`` (default ``{"message": ...}``) and
    reads the reply from ``response_path`` (dot/index, e.g. ``choices.0.message.content``)
    and tool calls from ``tool_calls_path``. Auth via ``headers`` or ``$CRUCIBLE_TARGET_AUTH``.
    Black-box (no config/clone).
    """

    def __init__(self, url: str, headers: dict | None = None, message_field: str = "message",
                 response_path: str = "text", tool_calls_path: str = "tool_calls",
                 body_extra: dict | None = None, timeout: float = 30.0):
        self.url = url
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        auth = os.environ.get("CRUCIBLE_TARGET_AUTH")
        if auth and "Authorization" not in self.headers:
            self.headers["Authorization"] = auth
        self.message_field = message_field
        self.response_path = response_path
        self.tool_calls_path = tool_calls_path
        self.body_extra = body_extra or {}
        self.timeout = timeout

    def send(self, message: str) -> Response:
        body = json.dumps({**self.body_extra, self.message_field: message}).encode()
        req = urllib.request.Request(self.url, data=body, headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                data = json.loads(resp.read().decode())
        except Exception:  # noqa: BLE001 — surface as an error, not "resisted"
            return Response(text="", error=True)
        text = _dig(data, self.response_path)
        if not isinstance(text, str):
            text = "" if text is None else json.dumps(text)
        calls = []
        raw = _dig(data, self.tool_calls_path)
        if isinstance(raw, list):
            for c in raw:
                if isinstance(c, dict):
                    calls.append(ToolCall(name=c.get("name", ""), args=c.get("args", {})))
        return Response(text=text, tool_calls=calls)

    def get_config(self) -> dict[str, Any] | None:
        return None

    def clone_with_config(self, patch: dict[str, Any]) -> "TargetAdapter | None":
        return None
