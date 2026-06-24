"""Real LLM red agent (constitution §1: Sonnet 4.6 on the inner red loop).

The detector CAUGHT this sample (score >= threshold). The agent asks the LLM to
propose ONE concrete, label-preserving mutation — drawn from the spec's
metamorphic relations — that drops the detector score below threshold while the
sample stays truly fraudulent. It applies the proposal, verifies it against the
real ``score_fn``/``label_fn`` (never trusts the LLM's word), and on success
records the strategy in the catalog and returns the mutated sample.

Cost is bounded from the start: a per-instance call counter is checked against
``max_calls`` BEFORE every provider call. When the budget is exhausted the agent
returns ``None`` so the caller (the HybridAdversary) falls back to the FREE
deterministic mutator — the loop never stalls and never overspends. It fails
loud on provider errors (no fabricated mutation).
"""

import dataclasses
import json
from collections.abc import Callable, Mapping
from typing import Any, cast

from shared.llm.base import LLMProvider
from shared.types import SealedSpec

from modules.red.catalog import StrategyCatalog

_SYSTEM = (
    "You are a red-team adversary probing a fraud detector for blind spots. A "
    "transaction was CAUGHT by the detector (its score is at or above the "
    "decision threshold). Propose ONE concrete, label-preserving mutation that "
    "lowers the detector's score BELOW the threshold while the transaction stays "
    "genuinely fraudulent. You may ONLY move a feature in a direction allowed by "
    "the listed metamorphic relations (those are the moves proven not to change "
    "the true fraud label). Return a single feature to change and its new "
    "numeric value, plus a one-sentence rationale."
)

_MUTATION_SCHEMA: Mapping[str, object] = {
    "type": "object",
    "properties": {
        "feature": {"type": "string"},
        "new_value": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["feature", "new_value", "rationale"],
    "additionalProperties": False,
}


def _field_names(sample: object) -> set[str]:
    if dataclasses.is_dataclass(sample) and not isinstance(sample, type):
        return {f.name for f in dataclasses.fields(sample)}
    return set()


def _relations_text(spec: SealedSpec) -> str:
    lines = [
        f"- feature={rel.feature!r} direction={rel.direction!r} "
        f"(label_must_change={rel.label_must_change}): {rel.description.strip()}"
        for rel in spec.metamorphic_relations
    ]
    return "\n".join(lines) if lines else "- (none declared)"


class LlmRedAdversary:
    """LLM-driven evasion adversary. Verifies every proposal against the oracle."""

    def __init__(
        self,
        provider: LLMProvider,
        spec: SealedSpec,
        score_fn: Callable[[object], float],
        label_fn: Callable[[object], bool],
        threshold: float,
        *,
        max_attempts: int = 3,
        max_calls: int | None = None,
        catalog: StrategyCatalog | None = None,
        prompt_suffix: str | None = None,
    ) -> None:
        self._provider = provider
        self._spec = spec
        self._score = score_fn
        self._is_positive = label_fn
        self._threshold = threshold
        self._max_attempts = max_attempts
        self._max_calls = max_calls
        self._catalog = catalog
        # Optional extra context appended to every prompt. The WHITE-BOX red pass
        # uses this to inject the oracles' verification scheme so the attacker is
        # informed about the verifiers it must also fool. ``None`` => black box.
        self._prompt_suffix = prompt_suffix
        self._calls_made = 0

    @property
    def calls_made(self) -> int:
        return self._calls_made

    def mutate(self, sample: object, score: float) -> object | None:
        fields = _field_names(sample)
        history: list[str] = []
        for _ in range(self._max_attempts):
            # Budget gate: never touch the provider past the cap. Return None so
            # the caller falls back to the free deterministic mutator.
            if self._max_calls is not None and self._calls_made >= self._max_calls:
                return None
            self._calls_made += 1
            resp = self._provider.complete(
                self._build_prompt(sample, score, history),
                system=_SYSTEM,
                max_tokens=512,
                json_schema=_MUTATION_SCHEMA,
            )
            parsed = json.loads(resp.text)  # fail loud on malformed provider output
            feat = str(parsed["feature"])
            raw_value = parsed["new_value"]

            if feat not in fields or isinstance(raw_value, bool) or not isinstance(
                raw_value, (int, float)
            ):
                history.append(
                    f"Rejected proposal feature={feat!r} value={raw_value!r}: "
                    "feature must be a real numeric field of the sample."
                )
                continue

            new_value = float(raw_value)
            candidate: object = dataclasses.replace(cast(Any, sample), **{feat: new_value})
            cand_score = self._score(candidate)
            still_fraud = self._is_positive(candidate)

            if cand_score < self._threshold and still_fraud:
                self._record(sample, candidate, feat)
                return candidate

            history.append(
                f"Tried feature={feat!r} new_value={new_value}: "
                f"score={cand_score:.4f} (threshold={self._threshold}), "
                f"still_fraud={still_fraud}. "
                + (
                    "It did not drop the score below threshold."
                    if cand_score >= self._threshold
                    else "It flipped the true label — not allowed."
                )
            )
        return None

    def _record(self, sample: object, candidate: object, feat: str) -> None:
        if self._catalog is None:
            return
        before = cast(float, getattr(sample, feat))
        after = cast(float, getattr(candidate, feat))
        direction = "decrease" if after < before else "increase"
        self._catalog.record(feature=feat, direction=direction, source="llm")

    def _build_prompt(self, sample: object, score: float, history: list[str]) -> str:
        features = (
            dataclasses.asdict(cast(Any, sample))
            if dataclasses.is_dataclass(sample) and not isinstance(sample, type)
            else {"sample": repr(sample)}
        )
        prompt = (
            "Transaction features:\n"
            f"{json.dumps(features, indent=2, default=str)}\n\n"
            f"Detector decision: CAUGHT as fraud "
            f"(detector_score={score} >= threshold={self._threshold}).\n\n"
            "Allowed label-preserving moves (metamorphic relations):\n"
            f"{_relations_text(self._spec)}\n\n"
            "Goal: pick ONE feature and a new numeric value so the detector "
            "score drops below the threshold while the transaction stays "
            "genuinely fraudulent."
        )
        if history:
            prompt += "\n\nPrior failed attempts this round (do not repeat):\n" + "\n".join(
                f"- {h}" for h in history
            )
        if self._prompt_suffix:
            prompt += "\n\n" + self._prompt_suffix
        return prompt
