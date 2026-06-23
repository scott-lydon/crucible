"""FraudPropertyFuzzOracle: property-based fuzzing over the producer's output
invariants (plan.md section 3). Uses `hypothesis` to search the neighbourhood of the
attack input for any case where the producer violates a declared output invariant:

  * fraud_probability stays in [0, 1]
  * label stays in {0, 1}
  * the producer is deterministic (same input -> same output)

A well-behaved classifier never violates these, so the oracle stays quiet on a sound
producer (low false-positive) and fires on a broken or reward-hacked one — exactly the
non-colluding diversity the ensemble needs. One vote (1.0), token-free. `derandomize`
makes the search reproducible, so the verdict replays (spec US-5)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from shared.types.core import Attack, OracleVote
from shared.types.enums import OracleKind
from shared.types.results import HealthStatus
from shared.types.sealed_spec import SealedSpec

PredictFn = Callable[[Mapping[str, Any]], dict[str, Any]]
_INVARIANT = "fraud_probability in [0,1]; label in {0,1}; producer is deterministic"


def find_violation(
    predict: PredictFn, base: Mapping[str, Any], feature_names: list[str],
    *, epsilon: float = 0.15, max_examples: int = 25,
) -> str | None:
    """Return a description of the first invariant violation hypothesis finds, or None."""
    base_f = {k: float(v) for k, v in base.items()}

    @settings(max_examples=max_examples, deadline=None, database=None, derandomize=True,
              suppress_health_check=list(HealthCheck))
    @given(deltas=st.lists(
        st.floats(min_value=-epsilon, max_value=epsilon, allow_nan=False, allow_infinity=False),
        min_size=len(feature_names), max_size=len(feature_names)))
    def _prop(deltas: list[float]) -> None:
        feats = {
            f: base_f.get(f, 0.0) * (1.0 + d)
            for f, d in zip(feature_names, deltas, strict=True)
        }
        out = predict(feats)
        prob = out.get("fraud_probability")
        label = out.get("label")
        assert isinstance(prob, int | float) and 0.0 <= float(prob) <= 1.0, (
            f"fraud_probability {prob} out of [0,1]")
        assert label in (0, 1), f"label {label} not in {{0,1}}"
        assert predict(feats) == out, "producer is non-deterministic"

    try:
        _prop()
    except AssertionError as exc:
        return str(exc).splitlines()[0]
    return None


class FraudPropertyFuzzOracle:
    kind: OracleKind = OracleKind.property_fuzz
    weight: float = 1.0

    def __init__(self, predict: PredictFn, feature_names: list[str]) -> None:
        self._predict = predict
        self._features = feature_names

    async def vote(
        self, spec: SealedSpec, attack: Attack, output: Mapping[str, Any]
    ) -> OracleVote:
        prob = output.get("fraud_probability")
        label = output.get("label")
        violation: str | None = None
        if not (isinstance(prob, int | float) and 0.0 <= float(prob) <= 1.0):
            violation = f"this output's fraud_probability {prob} is out of [0,1]"
        elif label not in (0, 1):
            violation = f"this output's label {label} is not in {{0,1}}"
        else:
            violation = find_violation(self._predict, attack.payload, self._features)

        fired = violation is not None
        reason = (
            f"Property-fuzz found an output-invariant violation: {violation}."
            if fired else
            "Output invariants held across fuzzed inputs: probability bounded, label "
            "binary, producer deterministic."
        )
        return OracleVote(
            oracle=self.kind, fired=fired, weight=self.weight, obligation=_INVARIANT,
            observation=f"invariant=({_INVARIANT}) violation={violation}",
            reason=reason, seed=attack.seed,
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(
            status="green", detail={"oracle": "property_fuzz", "engine": "hypothesis"}
        )
