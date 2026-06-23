"""Production LLM adapter for the Anthropic API (Claude Opus 4.8 / Sonnet 4.6).

Facts baked in here (from the Anthropic API reference — do not deviate):

* The 4.x models take adaptive thinking only and **reject** ``temperature``,
  ``top_p``, ``top_k``, and ``budget_tokens`` with a 400. None are passed.
* Per-model pricing ($/1M tokens, input/output): Opus 4.x $5/$25, Sonnet 4.6
  $3/$15, Haiku 4.5 $1/$5, Fable 5 $10/$50. Cost is reported per call so the
  ``dollars`` figure is HONEST per model — never Opus-priced for a Sonnet call.

The adapter fails loud: anthropic errors (e.g. ``anthropic.APIError``) propagate
unchanged rather than being swallowed.
"""

from collections.abc import Mapping
from typing import cast

import anthropic

from shared.llm.base import LLMResponse

DEFAULT_MODEL = "claude-opus-4-8"

# Per-token pricing ($/token, input, output) keyed by model id prefix.
# Longest matching prefix wins; unknown models fall back to Opus pricing
# (conservative — never under-reports cost).
_PRICING: tuple[tuple[str, float, float], ...] = (
    ("claude-fable-5", 10.0 / 1_000_000, 50.0 / 1_000_000),
    ("claude-opus", 5.0 / 1_000_000, 25.0 / 1_000_000),
    ("claude-sonnet", 3.0 / 1_000_000, 15.0 / 1_000_000),
    ("claude-haiku", 1.0 / 1_000_000, 5.0 / 1_000_000),
)
_FALLBACK_PRICE = (5.0 / 1_000_000, 25.0 / 1_000_000)


def _price_for(model: str) -> tuple[float, float]:
    best: tuple[float, float] | None = None
    best_len = -1
    for prefix, price_in, price_out in _PRICING:
        if model.startswith(prefix) and len(prefix) > best_len:
            best, best_len = (price_in, price_out), len(prefix)
    return best if best is not None else _FALLBACK_PRICE


def _cost(input_tokens: int, output_tokens: int, model: str = DEFAULT_MODEL) -> float:
    price_in, price_out = _price_for(model)
    return round(input_tokens * price_in + output_tokens * price_out, 6)


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
            dollars=_cost(input_tokens, output_tokens, str(resp.model)),
            raw=raw,
        )
