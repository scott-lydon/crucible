"""Typed LLM errors.

Loud and specific per coding-practices.md section 6: the message names the
model, the failing stage (spawn, timeout, exit code, or parse), and the
captured stderr so a failed call is diagnosable without a debugger.
"""

from __future__ import annotations

from shared.types import CrucibleError


class LlmCallError(CrucibleError):
    """A `claude` CLI call failed: non-zero exit, timeout, or unparseable output.

    The message includes the model and the likely fix (for example, run
    `claude` once interactively to confirm the Max session is authenticated).
    """


class NoLlmProviderError(CrucibleError):
    """No LLM provider could be resolved for a real run.

    Raised when the `claude` CLI is absent (deployed instance) and no Anthropic
    API key is available from the admin project-key path or the user-key path.
    The message names the two ways to supply one so the operator can fix it from
    the admin panel without reading the code.
    """


class AnthropicApiError(LlmCallError):
    """An Anthropic Messages API call failed: HTTP error or a model refusal.

    Subclasses `LlmCallError` so the run loop and FastAPI boundary surface an
    API-path failure the same way they surface a CLI-path failure. The message
    names the model, the HTTP status (when knowable), and the likely fix.
    """
