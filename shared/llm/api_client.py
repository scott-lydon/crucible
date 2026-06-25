"""Anthropic Messages API client (deploy-time fallback to the `claude` CLI).

The local path stays the `claude` CLI on the operator's Claude Max subscription
(coding-practices.md section 1, "LLM access path"). On a server with no CLI
session, the operator supplies a metered `ANTHROPIC_API_KEY`; this client is
that fallback. It implements the same `LlmClient` contract as `ClaudeCliClient`,
so the red, blue, and oracle pillars call it without knowing which path is live.

The Anthropic Messages API does not return a dollar cost, so we compute it from
`usage` token counts and the published per-model rates, and populate the same
`LlmResult.dollars` field the CLI path fills, keeping `/spend` and the
`llm_calls` transparency column real on a deployed run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from shared.llm.errors import AnthropicApiError
from shared.llm.models import LlmModel, LlmResult
from shared.types import Money

_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_MAX_TOKENS = 8000
_DEFAULT_TIMEOUT_SECONDS = 120.0

# Map the internal model enum to the public Messages API model ids. The CLI
# accepts the exact version strings in `LlmModel`, but the API expects the
# family aliases. Default an unknown member to opus so a new enum value never
# silently routes to the cheapest model.
_API_MODEL_IDS: dict[LlmModel, str] = {
    LlmModel.HAIKU: "claude-haiku-4-5",
    LlmModel.SONNET: "claude-sonnet-4-6",
    LlmModel.OPUS: "claude-opus-4-8",
}
_DEFAULT_API_MODEL_ID = "claude-opus-4-8"

# Published Anthropic pricing in dollars per one million tokens, (input, output).
# The API omits dollar cost, so cost = in/1e6*rate_in + out/1e6*rate_out keeps
# the transparency column honest on the deployed path.
_PRICING_PER_MTOK: dict[LlmModel, tuple[float, float]] = {
    LlmModel.HAIKU: (1.0, 5.0),
    LlmModel.SONNET: (3.0, 15.0),
    LlmModel.OPUS: (5.0, 25.0),
}
_DEFAULT_PRICING = (5.0, 25.0)


def _compute_cost(model: LlmModel, tokens_in: int, tokens_out: int) -> Money:
    """Dollar cost from token usage and the per-model rate, mirroring the CLI's
    `total_cost_usd`, so a deployed run reports real spend instead of zero."""
    rate_in, rate_out = _PRICING_PER_MTOK.get(model, _DEFAULT_PRICING)
    dollars = tokens_in / 1_000_000 * rate_in + tokens_out / 1_000_000 * rate_out
    return Money.of(dollars)


def parse_api_json(data: dict[str, Any], model: LlmModel) -> LlmResult:
    """Parse one Anthropic Messages API response object into an LlmResult.

    Narrows every field with isinstance rather than casting (coding-practices
    "narrow, do not cast"). A `stop_reason` of "refusal" raises instead of
    returning empty text as success, so a refusal is a loud, typed failure.
    """
    stop_reason = data.get("stop_reason")
    if stop_reason == "refusal":
        raise AnthropicApiError(
            f"Anthropic API refused the request for model {model.value!r} "
            f"(stop_reason='refusal'). Reframe the prompt: the call was declined "
            f"by the model, not by a transport error."
        )

    content = data.get("content")
    if not isinstance(content, list):
        raise AnthropicApiError(
            f"Anthropic API response for model {model.value!r} had no list "
            f"'content' field; keys present: {sorted(data)}."
        )
    text = "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    )

    usage = data.get("usage")
    usage_dict: dict[str, Any] = usage if isinstance(usage, dict) else {}
    raw_in = usage_dict.get("input_tokens", 0)
    raw_out = usage_dict.get("output_tokens", 0)
    tokens_in = raw_in if isinstance(raw_in, int) else 0
    tokens_out = raw_out if isinstance(raw_out, int) else 0

    msg_id = data.get("id")
    session_id = msg_id if isinstance(msg_id, str) else ""

    return LlmResult(
        text=text,
        model=model,
        dollars=_compute_cost(model, tokens_in, tokens_out),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        session_id=session_id,
        raw=data,
    )


@dataclass(frozen=True, slots=True)
class AnthropicApiClient:
    """Calls POST /v1/messages over httpx, implementing the `LlmClient` contract.

    The API key is held on the instance (constructor arg), never read from a
    module global, so the selector can hand the project key or the visitor's own
    key per the resolution order without mutating shared state.
    """

    api_key: str
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS

    async def call(
        self,
        prompt: str,
        *,
        model: LlmModel,
        system: str | None = None,
    ) -> LlmResult:
        # Adaptive thinking is the 4.x default; sending temperature, top_p,
        # top_k, or an explicit thinking/budget_tokens param makes those models
        # return 400, so the body carries only model, max_tokens, and messages
        # (plus an optional top-level system string).
        body: dict[str, Any] = {
            "model": _API_MODEL_IDS.get(model, _DEFAULT_API_MODEL_ID),
            "max_tokens": _MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system is not None:
            body["system"] = system
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as http:
                response = await http.post(_MESSAGES_URL, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise AnthropicApiError(
                f"Anthropic API request failed for model {model.value!r}: "
                f"{type(exc).__name__}. Confirm network egress to "
                f"api.anthropic.com and that the key is valid."
            ) from exc

        if response.status_code != 200:
            # Surface the API's own error message (no SQL or local paths) so the
            # operator sees "invalid api key" / "credit balance too low" rather
            # than a bare status code.
            detail = _error_detail(response)
            raise AnthropicApiError(
                f"Anthropic API returned {response.status_code} for model "
                f"{model.value!r}: {detail}. Confirm the ANTHROPIC_API_KEY is "
                f"valid and the account has credit."
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise AnthropicApiError(
                f"Anthropic API returned non-JSON for model {model.value!r}. "
                f"First bytes: {response.text[:200]!r}."
            ) from exc
        if not isinstance(data, dict):
            raise AnthropicApiError(
                f"Anthropic API JSON for model {model.value!r} was not an "
                f"object; got {type(data).__name__}."
            )
        return parse_api_json(data, model)


def _error_detail(response: httpx.Response) -> str:
    """The Messages API error message, or the raw body when it is not JSON."""
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200] or "(empty body)"
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            message = err.get("message")
            if isinstance(message, str):
                return message
    return str(payload)[:200]
