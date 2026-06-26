"""DISCOVER -> STRATEGIZE -> SOLVE red (CP discover_solve).

The synthesis we proved we needed live: pure-LLM red is a great strategist but a
poor one-shot numeric solver (1 evasion); the deterministic ladder is a good
solver but blind/strategy-less. This red lets the LLM OWN the strategy, a generic
solver land the numbers, and DISCOVERS the attack surface by probing (no hand-fed
``movable_features``).

FREE tier (MockProvider; fully in-process — ZERO real LLM calls):

  * the probe DISCOVERS the sensitivity map generically (no hardcoded fields);
  * given a mock LLM vector, the solver LANDS a multi-feature evasion (the victim
    clears AND the intent is preserved);
  * an intent-breaking solve is rejected;
  * a source-grep test asserts the module names ZERO target fields.

GATED LIVE (skipif no key): real Sonnet chooses the vectors against real caught
Sparkov frauds; reports the number of multi-feature evasions landed (target the
13-19 range, vs pure-LLM's 1) HONESTLY — the vectors the LLM chose + cost.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pytest

from modules.red.catalog import StrategyCatalog
from modules.red.discover_solve.adversary import DiscoverStrategizeSolveAdversary
from shared.llm.base import LLMResponse
from shared.types import SealedSpec, sealed_spec_from_yaml


# --- A scripted provider: returns queued payloads in order (free) -----------
class _ScriptedProvider:
    """``LLMProvider`` returning queued payloads in order (deterministic, free)."""

    def __init__(self, payloads: Sequence[str]) -> None:
        self._payloads = list(payloads)
        self._i = 0
        self.prompts: list[str] = []
        self.systems: list[str | None] = []

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        json_schema: Mapping[str, object] | None = None,
    ) -> LLMResponse:
        self.prompts.append(prompt)
        self.systems.append(system)
        text = self._payloads[min(self._i, len(self._payloads) - 1)]
        self._i += 1
        return LLMResponse(
            text=text, model="mock", input_tokens=0, output_tokens=0, dollars=0.0
        )


# --- A generic, queryable fake target + intent oracle (NOT the real victim) --
# A dataclass row with several numeric fields + a bool. The fake detector's score
# rises with two fields and is INSENSITIVE to a third; the intent oracle stays
# True only while a field stays above a floor — so an over-aggressive solve breaks
# intent. This proves the MECHANISM without the real victim or any LLM call.
@dataclass(frozen=True, slots=True)
class _FakeRow:
    txn_index: int
    big: float       # strongly raises the detector score
    medium: float    # mildly raises the detector score
    inert: float     # the detector ignores this entirely
    flag: bool = True  # a non-numeric field the probe must skip


_THRESHOLD = 0.5


def _fake_score(sample: object) -> float:
    """A monotone-in-(big, medium) score; ignores ``inert`` and the bool."""
    big = float(getattr(sample, "big"))
    medium = float(getattr(sample, "medium"))
    return 0.001 * big + 0.0005 * medium


def _intent_ok(sample: object) -> bool:
    """Intent preserved iff ``big`` stays above a floor (a genuine fraud still
    needs *some* magnitude); driving it to ~0 breaks the intent."""
    return float(getattr(sample, "big")) >= 100.0


def _spec() -> SealedSpec:
    path = pathlib.Path(__file__).resolve().parents[2] / "specs" / "fraud_v0.yaml"
    return sealed_spec_from_yaml(path.read_text())


def _caught_row() -> _FakeRow:
    # big=900 -> score 0.9 (caught). Lowering big toward (but not past) the 100
    # floor, combined with medium, can clear the 0.5 threshold while intent holds.
    return _FakeRow(txn_index=0, big=900.0, medium=400.0, inert=50.0)


# === FREE: the probe discovers the surface generically ======================


def test_probe_discovers_sensitivity_map_no_hardcoded_fields() -> None:
    """DISCOVER finds, by probing, which fields move the score and the direction
    that LOWERS it — over fields it never had named to it."""
    red = DiscoverStrategizeSolveAdversary(
        provider=_ScriptedProvider(["{}"]),
        spec=_spec(),
        score_fn=_fake_score,
        label_fn=_intent_ok,
        threshold=_THRESHOLD,
    )
    sample = _caught_row()
    baseline = {"big": 900.0, "medium": 400.0, "inert": 50.0}
    sens = red.discover(sample, baseline)

    # The numeric fields were discovered; the bool ``flag`` is NOT probed.
    assert set(sens) == {"big", "medium", "inert"}
    # The two score-driving fields are LOWERED by decreasing them.
    assert sens["big"].lowering_direction == "decrease"
    assert sens["medium"].lowering_direction == "decrease"
    # The inert field moves the score by ~nothing -> no lowering direction.
    assert sens["inert"].lowering_direction is None
    # ``big`` matters more than ``medium`` (bigger sensitivity magnitude).
    assert sens["big"].magnitude > sens["medium"].magnitude > sens["inert"].magnitude


# === FREE: the LLM chooses the vector, the solver LANDS it ==================


def test_llm_vector_drives_multi_feature_solve_that_lands() -> None:
    """Given a mock LLM vector (decrease big AND medium — a COMBINED move), the
    generic solver lands an evasion: victim clears AND intent preserved."""
    catalog = StrategyCatalog()
    provider = _ScriptedProvider([
        '{"moves": [{"feature": "big", "direction": "decrease"}, '
        '{"feature": "medium", "direction": "decrease"}], '
        '"rationale": "both raise the score; lower them together to clear"}'
    ])
    red = DiscoverStrategizeSolveAdversary(
        provider=provider,
        spec=_spec(),
        score_fn=_fake_score,
        label_fn=_intent_ok,
        threshold=_THRESHOLD,
        catalog=catalog,
    )
    sample = _caught_row()
    assert _fake_score(sample) >= _THRESHOLD  # genuinely caught to start

    landed = red.mutate(sample, _fake_score(sample))

    assert landed is not None
    # Objective verdict: the victim CLEARS and the intent is PRESERVED.
    assert _fake_score(landed) < _THRESHOLD
    assert _intent_ok(landed) is True
    # It was a genuine MULTI-feature landing: both chosen fields moved.
    assert float(getattr(landed, "big")) < 900.0
    assert float(getattr(landed, "medium")) < 400.0
    assert float(getattr(landed, "big")) >= 100.0  # intent floor respected
    # The LLM-chosen vector + rationale is recorded as solved (provenance).
    prov = catalog.vector_provenance()
    assert len(prov) == 1
    assert prov[0].solved is True
    assert dict(prov[0].directions) == {"big": "decrease", "medium": "decrease"}
    assert "lower" in prov[0].rationale.lower()
    # The per-feature view tags the source as discover_solve (not a blind ladder).
    assert any(
        row["feature"] == "big" and row["source"] == "discover_solve"
        for row in catalog.summary()
    )


def test_intent_breaking_solve_is_rejected() -> None:
    """If the only vector the LLM offers cannot clear WITHOUT breaking the intent,
    the solver lands NOTHING (no evasion is reported, intent is never sacrificed).

    Here the LLM insists on moving ONLY ``medium`` — but medium alone cannot drag
    the score below threshold (big=900 already scores 0.9), so no rung clears."""
    provider = _ScriptedProvider([
        '{"moves": [{"feature": "medium", "direction": "decrease"}], '
        '"rationale": "lower medium"}'
    ])
    red = DiscoverStrategizeSolveAdversary(
        provider=provider,
        spec=_spec(),
        score_fn=_fake_score,
        label_fn=_intent_ok,
        threshold=_THRESHOLD,
        max_iters=1,
    )
    sample = _caught_row()
    assert red.mutate(sample, _fake_score(sample)) is None


def test_solver_never_returns_an_intent_breaking_candidate() -> None:
    """Directly assert the solve guard: even told to crush ``big`` to zero, the
    solver only returns a candidate whose intent is preserved — it rejects rungs
    that fall below the intent floor."""
    red = DiscoverStrategizeSolveAdversary(
        provider=_ScriptedProvider(["{}"]),
        spec=_spec(),
        score_fn=_fake_score,
        label_fn=_intent_ok,
        threshold=_THRESHOLD,
    )
    sample = _caught_row()
    baseline = {"big": 900.0, "medium": 400.0, "inert": 50.0}
    landed = red.solve(sample, baseline, {"big": "decrease"})
    # Any landing must preserve intent (big >= 100); big alone may or may not clear
    # at a rung that keeps intent — but it is NEVER returned with intent broken.
    if landed is not None:
        assert _intent_ok(landed) is True
        assert _fake_score(landed) < _THRESHOLD


def test_calls_made_respects_budget() -> None:
    """With ``max_llm_calls=0`` the red never touches the provider and lands None."""
    provider = _ScriptedProvider([
        '{"moves": [{"feature": "big", "direction": "decrease"}], "rationale": "x"}'
    ])
    red = DiscoverStrategizeSolveAdversary(
        provider=provider,
        spec=_spec(),
        score_fn=_fake_score,
        label_fn=_intent_ok,
        threshold=_THRESHOLD,
        max_llm_calls=0,
    )
    assert red.mutate(_caught_row(), 0.9) is None
    assert red.calls_made == 0
    assert provider.prompts == []  # discover may query score_fn, never the LLM


# === FREE: target-agnostic by construction (zero target field names) ========


def test_module_names_zero_target_fields() -> None:
    """A source-grep proving the module hardcodes NO target-specific field name —
    the attack surface is DISCOVERED, never hand-fed. (Guards agnosticism.)

    Matches whole identifiers (word boundaries) so substrings inside ordinary
    English ("manage" -> "age", "transaction" -> ...) do not false-positive."""
    import re

    src = (
        pathlib.Path(__file__).resolve().parents[2]
        / "modules" / "red" / "discover_solve" / "adversary.py"
    ).read_text()
    # The Sparkov victim's field names + the synth victim's — none may appear as
    # a whole identifier token.
    forbidden = (
        "amt", "cat_risk", "merchant_risk", "city_pop", "geo_distance_km",
        "velocity", "day_of_week", "hour", "age", "txn_index", "is_fraud",
    )
    for name in forbidden:
        assert re.search(rf"\b{re.escape(name)}\b", src) is None, (
            f"module names target field {name!r}"
        )


# === GATED LIVE: real Sonnet chooses vectors vs real caught Sparkov frauds ===


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="no ANTHROPIC_API_KEY")
def test_live_sonnet_discover_solve_lands_multi_feature_evasions() -> None:
    """Real Sonnet chooses the vectors; the solver lands them against REAL caught
    Sparkov frauds. Reports HONESTLY how many multi-feature evasions landed (vs
    pure-LLM's 1) and what vectors the LLM chose. Bounded budget."""
    from examples.targets import fraud_sparkov
    from modules.targets.local_model.adapter import LocalModelTarget
    from shared.llm.anthropic_api import AnthropicApiProvider

    detector = LocalModelTarget(
        model_path=fraud_sparkov.MODEL_PATH,
        feature_names=fraud_sparkov.DETECTOR_FEATURES,
    )
    threshold = fraud_sparkov.DETECTOR_THRESHOLD
    label_fn = fraud_sparkov.is_fraud
    catalog = StrategyCatalog()
    red = DiscoverStrategizeSolveAdversary(
        provider=AnthropicApiProvider(model="claude-sonnet-4-6"),
        spec=fraud_sparkov.load_spec(),
        score_fn=detector.score,
        label_fn=label_fn,
        threshold=threshold,
        max_iters=3,
        max_llm_calls=40,  # bounded spend
        catalog=catalog,
    )
    # Caught true-fraud samples (the red only ever attacks these).
    batch = fraud_sparkov.generate_batch("live", 200)
    caught = [
        t for t in batch
        if label_fn(t) and detector.score(t) >= threshold
    ][:20]
    assert caught, "no caught frauds to attack"

    landed = 0
    multi = 0
    vectors: list[dict[str, str]] = []
    for sample in caught:
        result = red.mutate(sample, detector.score(sample))
        if result is not None:
            landed += 1
    for prov in catalog.vector_provenance():
        if prov.solved:
            vectors.append(dict(prov.directions))
            if len(prov.directions) >= 2:
                multi += 1

    print(
        f"\n[LIVE discover_solve] caught={len(caught)} landed={landed} "
        f"multi_feature={multi} llm_calls={red.calls_made} vectors={vectors}"
    )
    # HONEST: we assert the loop RAN within budget and report the count — not a
    # forced number. The mechanism is proven by the free tests; this measures it.
    assert red.calls_made <= 40
