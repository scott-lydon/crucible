"""Production LLM adapter for the Anthropic API (Claude Opus 4.8).

Opus 4.8 facts baked in here (from the Anthropic API reference — do not deviate):

* Model id is ``claude-opus-4-8``.
* Opus 4.8 takes adaptive thinking only and **rejects** ``temperature``,
  ``top_p``, ``top_k``, and ``budget_tokens`` with a 400. None are passed.
* Pricing is $5.00 / 1M input tokens, $25.00 / 1M output tokens.

The adapter fails loud: anthropic errors (e.g. ``anthropic.APIError``) propagate
unchanged rather than being swallowed.
"""

from collections.abc import Mapping
from typing import cast

import anthropic

from shared.llm.base import LLMResponse

DEFAULT_MODEL = "claude-opus-4-8"

# Opus 4.8 pricing, expressed per-token so cost is a plain multiply.
PRICE_IN_PER_TOKEN = 5.0 / 1_000_000
PRICE_OUT_PER_TOKEN = 25.0 / 1_000_000


def _cost(input_tokens: int, output_tokens: int) -> float:
    return round(
        input_tokens * PRICE_IN_PER_TOKEN + output_tokens * PRICE_OUT_PER_TOKEN,
        6,
    )


class AnthropicApiProvider:
    """``LLMProvider`` adapter backed by the real Anthropic Messages API.

    Inject ``client`` to make the adapter unit-testable; when ``None`` a real
    ``anthropic.Anthropic()`` is constructed (it reads ``ANTHROPIC_API_KEY`` from
    the environment).
    """

    def __init__(self, model: str = DEFAULT_MODEL, client: object | None = None) -> None:
        self.model = model
        # `anthropic.Anthropic()` reads ANTHROPIC_API_KEY from the env.
        self._client = anthropic.Anthropic() if client is None else client

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        json_schema: Mapping[str, object] | None = None,
    ) -> LLMResponse:
        # Build kwargs incrementally so we omit `system`/`output_config` rather
        # than pass nulls, and so we never pass any rejected sampling param.
        kwargs: dict[str, object] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system is not None:
            kwargs["system"] = system
        if json_schema is not None:
            kwargs["output_config"] = {
                "format": {"type": "json_schema", "schema": dict(json_schema)}
            }

        resp = self._client.messages.create(**kwargs)  # type: ignore[attr-defined]

        text = "".join(b.text for b in resp.content if b.type == "text")
        input_tokens = int(resp.usage.input_tokens)
        output_tokens = int(resp.usage.output_tokens)

        to_dict = getattr(resp, "to_dict", None)
        raw = cast("Mapping[str, object]", to_dict()) if callable(to_dict) else {}

        return LLMResponse(
            text=text,
            model=str(resp.model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            dollars=_cost(input_tokens, output_tokens),
            raw=raw,
        )
