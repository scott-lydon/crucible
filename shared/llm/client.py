"""LLM client over the local `claude` CLI.

LLM access runs through the operator's Claude Max subscription via the `claude`
command-line interface (ARCHITECTURE.md decision table), so local development
and the demo need no metered key. The CLI still reports `total_cost_usd` per
call, which feeds the dashboard cost column.

`ScriptedLlmClient` backs the mock-LLM mode (US-15): it returns fixture
responses and is selected by the `MOCK_LLM` setting, so a mock run is an
explicit, configured choice, never an undisclosed substitution.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from shared.config import Settings, get_settings
from shared.llm.active_key import ActiveKey, KeySource, get_active_key, get_prefer_api
from shared.llm.api_client import AnthropicApiClient
from shared.llm.errors import LlmCallError, NoLlmProviderError
from shared.llm.models import LlmModel, LlmResult
from shared.types import Money

_DEFAULT_TIMEOUT_SECONDS = 180.0


@runtime_checkable
class LlmClient(Protocol):
    """The contract every LLM caller (red, blue, oracles) depends on."""

    async def call(
        self,
        prompt: str,
        *,
        model: LlmModel,
        system: str | None = None,
    ) -> LlmResult:
        """Return the model's completion for one prompt, with cost and usage."""
        ...


def parse_cli_json(raw: bytes, model: LlmModel) -> LlmResult:
    """Parse the `claude --output-format json` payload into an LlmResult.

    Narrows every field with isinstance rather than casting, so malformed
    output raises a typed error instead of silently coercing (coding-practices
    "narrow, do not cast").
    """
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        snippet = raw[:200].decode("utf-8", errors="replace")
        raise LlmCallError(
            f"claude CLI returned output that is not JSON for model "
            f"{model.value!r}. First bytes: {snippet!r}."
        ) from exc

    if not isinstance(data, dict):
        raise LlmCallError(
            f"claude CLI JSON for model {model.value!r} was not an object; "
            f"got {type(data).__name__}."
        )
    if data.get("is_error"):
        raise LlmCallError(
            f"claude CLI reported an error for model {model.value!r}: "
            f"{data.get('result') or data.get('subtype') or 'unknown error'}."
        )

    result = data.get("result")
    if not isinstance(result, str):
        raise LlmCallError(
            f"claude CLI JSON for model {model.value!r} had no string 'result' "
            f"field; keys present: {sorted(data)}."
        )

    cost_raw = data.get("total_cost_usd", 0)
    cost = Money.of(cost_raw) if isinstance(cost_raw, (int, float)) else Money.zero()

    usage = data.get("usage")
    usage_dict: dict[str, Any] = usage if isinstance(usage, dict) else {}
    tokens_in = usage_dict.get("input_tokens", 0)
    tokens_out = usage_dict.get("output_tokens", 0)

    session = data.get("session_id")
    session_id = session if isinstance(session, str) else ""

    return LlmResult(
        text=result,
        model=model,
        dollars=cost,
        tokens_in=tokens_in if isinstance(tokens_in, int) else 0,
        tokens_out=tokens_out if isinstance(tokens_out, int) else 0,
        session_id=session_id,
        raw=data,
    )


@dataclass(frozen=True, slots=True)
class ClaudeCliClient:
    """Calls `claude -p --output-format json --model <m>`, prompt over stdin."""

    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS

    async def call(
        self,
        prompt: str,
        *,
        model: LlmModel,
        system: str | None = None,
    ) -> LlmResult:
        # Operator overrides (default: none -> production behavior unchanged):
        #   CRUCIBLE_LLM_MODEL_OVERRIDE forces every call to one model (e.g. a
        #     cheap/fast haiku validation pass before spending on sonnet/opus).
        #   CRUCIBLE_LLM_TIMEOUT_SECONDS raises the per-call CLI timeout.
        _override = os.environ.get("CRUCIBLE_LLM_MODEL_OVERRIDE", "").strip()
        if _override:
            try:
                model = LlmModel(_override)
            except ValueError:
                pass
        _timeout = self.timeout_seconds
        _env_timeout = os.environ.get("CRUCIBLE_LLM_TIMEOUT_SECONDS", "").strip()
        if _env_timeout:
            try:
                _timeout = float(_env_timeout)
            except ValueError:
                pass
        args = ["claude", "-p", "--output-format", "json", "--model", model.value]
        if system is not None:
            args += ["--append-system-prompt", system]
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise LlmCallError(
                "claude CLI not found on PATH. Install it and run `claude` once "
                "to authenticate the Claude Max session, or set ANTHROPIC_API_KEY "
                "for a server deploy without the CLI."
            ) from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")),
                timeout=_timeout,
            )
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise LlmCallError(
                f"claude CLI timed out after {_timeout:.0f}s for model "
                f"{model.value!r}. Raise the timeout or shorten the prompt."
            ) from exc

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise LlmCallError(
                f"claude CLI exited {proc.returncode} for model {model.value!r}. "
                f"stderr: {err or '(empty)'}. Confirm the Max session is "
                f"authenticated by running `claude` once interactively."
            )

        return parse_cli_json(stdout, model)


@dataclass(frozen=True, slots=True)
class ScriptedLlmClient:
    """Mock-LLM client (US-15): returns fixture text, never calls the CLI.

    Selected by the MOCK_LLM setting. Cost is zero and the raw payload is
    flagged `mock` so a mock run is unmistakable in the trace card.
    """

    responses: dict[LlmModel, str] = field(default_factory=dict)
    default_text: str = "mock response"

    async def call(
        self,
        prompt: str,
        *,
        model: LlmModel,
        system: str | None = None,
    ) -> LlmResult:
        text = self.responses.get(model, self.default_text)
        return LlmResult(
            text=text,
            model=model,
            dollars=Money.zero(),
            tokens_in=0,
            tokens_out=0,
            session_id="mock",
            raw={"mock": True, "model": model.value, "prompt_chars": len(prompt)},
        )


class ProviderMode(StrEnum):
    """Which LLM path is live, for the selector and the provider indicator."""

    MOCK = "mock"
    CLI = "cli"
    PROJECT_KEY = "project_key"
    USER_KEY = "user_key"
    NONE = "none"


def _cli_available() -> bool:
    """True when the `claude` CLI is on PATH (the local operator path)."""
    return shutil.which("claude") is not None


def resolve_provider_mode(settings: Settings | None = None) -> ProviderMode:
    """The active provider, by the same order `get_llm_client` selects.

    Single-sourced so the `/llm-provider` indicator and the actual selection
    can never disagree. Resolution order:
      1. MOCK_LLM set                 -> MOCK   (keeps the existing mock test path)
      2. prefer-API on AND active key -> PROJECT_KEY or USER_KEY (operator chose
         the metered API for speed, so it wins over the CLI even when present)
      3. `claude` on PATH             -> CLI    (the local operator path)
      4. an active key store          -> PROJECT_KEY or USER_KEY (deployed fallback)
      5. otherwise                    -> NONE   (no real provider; never silent mock)
    """
    resolved = settings if settings is not None else get_settings()
    if resolved.mock_llm:
        return ProviderMode.MOCK

    def _key_mode(key: ActiveKey) -> ProviderMode:
        return (
            ProviderMode.PROJECT_KEY
            if key.source is KeySource.PROJECT
            else ProviderMode.USER_KEY
        )

    active = get_active_key()
    # The operator's "prefer API for runs" toggle: when on and a key exists, the
    # metered API path wins over the local CLI so runs are fast (~1-3s vs the
    # CLI's ~10-40s). When the toggle is on but no key is set, fall through to
    # the CLI (or NONE) honestly rather than claiming an API that cannot run.
    if get_prefer_api() and active is not None:
        return _key_mode(active)
    if _cli_available():
        return ProviderMode.CLI
    if active is not None:
        return _key_mode(active)
    return ProviderMode.NONE


def get_llm_client(settings: Settings | None = None) -> LlmClient:
    """Resolve the live LLM client for a real (or mock) run.

    Order: mock when configured; else the local `claude` CLI when present; else
    the Anthropic API with the active fallback key (project key after admin
    login, or the visitor's own key). When no provider is available the call
    raises `NoLlmProviderError` instead of silently degrading to mock, so a run
    that asked for a real provider never returns fabricated output.

    The active key reaches detached background-run execution through the
    process-level store in `shared.llm.active_key`, written by the admin-login
    and user-key endpoints and read here at client construction time.
    """
    resolved = settings if settings is not None else get_settings()
    mode = resolve_provider_mode(resolved)
    if mode is ProviderMode.MOCK:
        return ScriptedLlmClient()
    if mode is ProviderMode.CLI:
        return ClaudeCliClient()
    if mode in (ProviderMode.PROJECT_KEY, ProviderMode.USER_KEY):
        active = get_active_key()
        # resolve_provider_mode just confirmed an active key exists; the guard
        # keeps mypy honest and turns a race (key cleared between calls) into a
        # typed error instead of an AttributeError.
        if active is None:
            raise NoLlmProviderError(
                "Active LLM key disappeared between resolution and use. "
                "Re-enter the Anthropic API key via the admin panel."
            )
        return AnthropicApiClient(api_key=active.value)
    raise NoLlmProviderError(
        "No LLM provider available: the `claude` CLI is not on PATH and no "
        "Anthropic API key is set. Enable the project key via admin login "
        "(if ANTHROPIC_API_KEY is configured on the server) or provide your "
        "own Anthropic API key in the admin panel."
    )
