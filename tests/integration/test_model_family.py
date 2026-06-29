"""The differential reference picker: different family when possible, GRACEFUL FALLBACK (never
halt) when the producer family is unknown or nothing differs (plan.md §199)."""
from __future__ import annotations

from shared.model_family import family, pick_differential_model

_DEF = "anthropic/claude-opus-4.8"


def test_family_parses_vendor_prefix() -> None:
    assert family("anthropic/claude-opus-4.8") == "anthropic"
    assert family("openai/gpt-5.5") == "openai"
    assert family("local-model") == ""        # no '/' -> unknown family
    assert family("") == ""


def test_claude_producer_gets_a_non_claude_reference() -> None:
    model, cross = pick_differential_model("anthropic/claude-sonnet-4.6", default=_DEF)
    assert family(model) != "anthropic"
    assert cross is True


def test_openai_producer_gets_a_non_openai_reference() -> None:
    model, cross = pick_differential_model("openai/gpt-5", default=_DEF)
    assert family(model) != "openai"
    assert cross is True


def test_unknown_producer_family_falls_back_and_never_halts() -> None:
    # The key robustness case: a producer whose family we cannot determine must NOT stop a run.
    model, cross = pick_differential_model("some-byo-model-no-prefix", default=_DEF)
    assert model == _DEF          # graceful fallback to the default
    assert cross is False         # independence not guaranteed, but the run proceeds


def test_no_different_family_in_pool_falls_back() -> None:
    # Producer + the only pooled model share a family -> can't differ -> fall back, don't halt.
    model, cross = pick_differential_model(
        "openai/gpt-5", default=_DEF, pool=("openai/gpt-5.5",))
    assert model == _DEF
    assert cross is False


def test_explicit_override_always_wins() -> None:
    model, cross = pick_differential_model(
        "anthropic/claude-sonnet-4.6", default=_DEF, override="openai/gpt-5.5")
    assert model == "openai/gpt-5.5"
    assert cross is True
    # override that happens to be same family is respected, but flagged not-cross-family
    model2, cross2 = pick_differential_model(
        "anthropic/claude-sonnet-4.6", default=_DEF, override="anthropic/claude-opus-4.8")
    assert model2 == "anthropic/claude-opus-4.8"
    assert cross2 is False
