"""Pick the differential oracle's REFERENCE model so it's a DIFFERENT family than the
producer (plan.md §199: same family shares blind spots — measured, both Claude models missed
an arithmetic error three other vendors caught).

The cardinal rule here is GRACEFUL DEGRADATION: this never raises and never blocks a run. If
the producer's family can't be determined, or no different-family model is available, it falls
back to a sensible default and reports cross_family=False — the run continues, independence is
simply annotated as not-guaranteed rather than halting."""

from __future__ import annotations

# Governance-safe, capable defaults (US / Anthropic). Ordered by our measured eval (gpt-5.5
# first). Deliberately excludes Qwen/DeepSeek: Qwen scored best but is an Alibaba (Chinese)
# lab — a data-governance concern for SR 11-7 customers; DeepSeek was too weak (3/8).
DEFAULT_POOL: tuple[str, ...] = (
    "openai/gpt-5.5",
    "anthropic/claude-opus-4.8",
    "google/gemini-3.5-flash",
)


def family(model: str) -> str:
    """The vendor/lineage prefix of an OpenRouter model id
    ('anthropic/claude-opus-4.8' -> 'anthropic'). An id with no '/' (or empty) returns ''
    meaning 'family unknown' — handled gracefully by the caller, never an error."""
    return model.split("/", 1)[0].lower() if model and "/" in model else ""


def pick_differential_model(
    producer_model: str,
    *,
    default: str,
    override: str | None = None,
    pool: tuple[str, ...] = DEFAULT_POOL,
) -> tuple[str, bool]:
    """Choose the differential reference model. Returns ``(model, cross_family)``.

    Precedence: (1) an explicit operator ``override`` always wins (we still report whether it
    happens to differ in family); (2) otherwise the first pooled model whose family differs
    from the producer's; (3) otherwise ``default`` with ``cross_family=False``. Never raises —
    an unknown producer family or an empty pool simply takes the graceful fallback so a run is
    never halted over lineage ambiguity."""
    if override:
        prod = family(producer_model)
        return override, bool(prod) and family(override) != prod
    prod = family(producer_model)
    if prod:  # producer family is known — try to pick a different one
        for candidate in pool:
            if family(candidate) and family(candidate) != prod:
                return candidate, True
    # Producer family unknown, or nothing in the pool differs: fall back, don't halt.
    return default, False
