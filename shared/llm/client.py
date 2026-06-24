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
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from shared.config import Settings, get_settings
from shared.llm.errors import LlmCallError
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
                timeout=self.timeout_seconds,
            )
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise LlmCallError(
                f"claude CLI timed out after {self.timeout_seconds:.0f}s for model "
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


def get_llm_client(settings: Settings | None = None) -> LlmClient:
    """Return the scripted client when MOCK_LLM is set, else the real CLI client."""
    resolved = settings if settings is not None else get_settings()
    if resolved.mock_llm:
        return ScriptedLlmClient()
    return ClaudeCliClient()
