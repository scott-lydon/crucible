"""HttpAgentTarget: the advanced BYO path. The user's agent already runs behind an
HTTP endpoint; the platform red-teams it as a black box. ``submit`` POSTs the crafted
input to the endpoint and reads the agent's reply out of the JSON response (a
configurable dotted field, or the raw body). The producer is entirely the user's — we
hold only its URL — so the sealed spec stays unreachable from it (constitution.md
section 3).

The endpoint is never pinged from /health (it may be the user's production system, and
a poll would be rude and possibly billed); ``probe`` is the explicit connectivity
check the loop runs once at run start."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from modules.targets.agent.target import AgentTarget
from shared.types.core import AuditTrace
from shared.types.enums import Pillar, Shape
from shared.types.results import HealthStatus, ProducerResult

HTTP_AGENT_KIND = "http_agent"


@dataclass(frozen=True, slots=True)
class HttpEndpointConfig:
    """How to call a user-hosted agent endpoint."""

    name: str
    endpoint: str
    input_field: str = "input"
    # Dotted path into the JSON response holding the agent's reply (list indices allowed,
    # e.g. "choices.0.message.content"). Empty string = use the raw response body.
    output_field: str = "output"
    method: str = "POST"
    headers: Mapping[str, str] = field(default_factory=dict)
    timeout: float = 60.0
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "endpoint": self.endpoint,
            "input_field": self.input_field,
            "output_field": self.output_field,
            "method": self.method,
            "headers": dict(self.headers),
            "timeout": self.timeout,
            "description": self.description,
        }


def _dig(data: Any, dotted: str) -> Any | None:
    """Navigate a JSON value by a dotted path; list indices allowed. None if absent."""
    current = data
    for part in dotted.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


class HttpAgentTarget:
    shape: Shape = Shape.shape2_agent
    kind: str = HTTP_AGENT_KIND

    def __init__(
        self, config: HttpEndpointConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._config = config
        # An injectable transport lets tests drive the endpoint with httpx.MockTransport
        # while production uses the default network transport.
        self._transport = transport

    @property
    def config(self) -> HttpEndpointConfig:
        return self._config

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._config.timeout, transport=self._transport)

    def _read_reply(self, resp: httpx.Response) -> str:
        if not self._config.output_field:
            return resp.text
        try:
            data = resp.json()
        except ValueError:
            return resp.text
        found = _dig(data, self._config.output_field)
        if found is None:
            return resp.text
        return found if isinstance(found, str) else str(found)

    async def submit(self, payload: Mapping[str, Any]) -> ProducerResult:
        user_input = AgentTarget._extract_input(payload)
        body = {self._config.input_field: user_input}
        async with self._client() as client:
            resp = await client.request(
                self._config.method, self._config.endpoint,
                json=body, headers=dict(self._config.headers),
            )
            resp.raise_for_status()
        reply = self._read_reply(resp)
        return ProducerResult(
            output={"response": reply, "endpoint": self._config.endpoint},
            audit=AuditTrace(
                pillar=Pillar.targets,
                summary=(
                    f"http agent '{self._config.name}' -> "
                    f"{resp.status_code} ({len(reply)} chars)"
                ),
                detail={
                    "agent": self._config.name,
                    "endpoint": self._config.endpoint,
                    "status_code": resp.status_code,
                    "input_preview": user_input[:300],
                },
            ),
        )

    async def probe(self) -> HealthStatus:
        """Explicit connectivity check (run once at run start, not on /health). Sends a
        benign ping and reports whether the endpoint answers."""
        try:
            async with self._client() as client:
                resp = await client.request(
                    self._config.method, self._config.endpoint,
                    json={self._config.input_field: "ping"},
                    headers=dict(self._config.headers),
                )
            ok = resp.status_code < 500
            return HealthStatus(
                status="green" if ok else "red",
                detail={"target": self.kind, "endpoint": self._config.endpoint,
                        "status_code": resp.status_code},
            )
        except Exception as exc:  # noqa: BLE001 — surface endpoint-down as red, not a crash
            return HealthStatus(
                status="red", detail={"target": self.kind, "endpoint": self._config.endpoint},
                error=str(exc),
            )

    async def health(self) -> HealthStatus:
        # Cheap, no network: a user endpoint must not be polled on every /health tick.
        status = "green" if self._config.endpoint else "amber"
        return HealthStatus(
            status=status,
            detail={"target": self.kind, "agent": self._config.name,
                    "endpoint": self._config.endpoint},
            error=None if self._config.endpoint else "no endpoint configured",
        )
