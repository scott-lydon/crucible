"""Blue proposer — reads the red loop's evasion catalog, proposes a patch.

Given the catalog of successful evasions (which feature the adversary moved, in
which direction, how often) plus the detector's CURRENT feature set and the
AVAILABLE feature menu, the proposer asks which currently-unused features to add
to close the blind spot. With a real provider it prompts Sonnet 4.6
(constitution §1: Sonnet on the inner loops) for a structured answer; budget is
bounded by ``max_calls`` checked BEFORE every provider call. When the budget is
exhausted (or a budget-0 / mock-shaped provider is used) it falls back to a
deterministic heuristic — propose every available feature not already in use —
so the loop ALWAYS produces a usable patch, honestly. It fails loud on real
provider errors (no fabricated patch).
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from shared.llm.base import LLMProvider

_SYSTEM = (
    "You are a blue-team defender hardening a fraud detector. The detector was "
    "trained on a narrow set of features and an adversary has been evading it by "
    "moving those features. You are given the catalog of successful evasions and "
    "the menu of features the model COULD be trained on but currently is not. "
    "Pick the unused features whose addition would most likely close the blind "
    "spot the adversary is exploiting. Only choose from the available features "
    "that are not already in the current set. Return the features to add and a "
    "one-sentence rationale."
)

_PATCH_SCHEMA: Mapping[str, object] = {
    "type": "object",
    "properties": {
        "features_to_add": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
    },
    "required": ["features_to_add", "rationale"],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class ProposedPatch:
    """A defender patch: which unused features to add, and why."""

    features_to_add: list[str] = field(default_factory=list)
    rationale: str = ""


class BlueProposer:
    """Proposes which unused features to add to harden the detector."""

    def __init__(self, provider: LLMProvider, *, max_calls: int | None = None) -> None:
        self._provider = provider
        self._max_calls = max_calls
        self._calls_made = 0

    @property
    def calls_made(self) -> int:
        return self._calls_made

    def propose(
        self,
        catalog_summary: Sequence[Mapping[str, object]],
        current_features: Sequence[str],
        available_features: Sequence[str],
    ) -> ProposedPatch:
        """Propose a patch. LLM when budgeted, deterministic heuristic otherwise."""
        unused = [f for f in available_features if f not in set(current_features)]

        # Budget gate: never touch the provider past the cap. Fall back to the
        # honest deterministic heuristic so the loop always produces a patch.
        if self._max_calls is not None and self._calls_made >= self._max_calls:
            return self._heuristic(unused)

        self._calls_made += 1
        resp = self._provider.complete(
            self._build_prompt(catalog_summary, current_features, available_features),
            system=_SYSTEM,
            max_tokens=512,
            json_schema=_PATCH_SCHEMA,
        )
        parsed = json.loads(resp.text)  # fail loud on malformed provider output
        raw = parsed.get("features_to_add", [])
        if not isinstance(raw, list):
            raise ValueError(
                f"BlueProposer: provider returned non-list features_to_add: {raw!r}"
            )
        # Keep only real, currently-unused features (never trust the model to
        # respect the menu); drop anything bogus or already deployed.
        unused_set = set(unused)
        features = [str(f) for f in raw if str(f) in unused_set]
        if not features:
            # The model proposed nothing usable — fall back honestly rather than
            # ship an empty patch that would retrain on the unchanged feature set.
            return self._heuristic(unused)
        rationale = str(parsed.get("rationale", "")).strip()
        return ProposedPatch(features_to_add=features, rationale=rationale)

    @staticmethod
    def _heuristic(unused: Sequence[str]) -> ProposedPatch:
        return ProposedPatch(
            features_to_add=list(unused),
            rationale=(
                "Deterministic fallback: add every available feature the deployed "
                "detector is not yet using to close its blind spot."
            ),
        )

    @staticmethod
    def _build_prompt(
        catalog_summary: Sequence[Mapping[str, object]],
        current_features: Sequence[str],
        available_features: Sequence[str],
    ) -> str:
        unused = [f for f in available_features if f not in set(current_features)]
        return (
            "Successful evasions recorded by the red loop "
            "(feature moved, direction, source, count):\n"
            f"{json.dumps(list(catalog_summary), indent=2, default=str)}\n\n"
            f"Detector's CURRENT features: {list(current_features)}\n"
            f"AVAILABLE features (full menu): {list(available_features)}\n"
            f"UNUSED features you may add: {unused}\n\n"
            "Goal: choose the unused features whose addition would best close the "
            "blind spot the recorded evasions exploit."
        )
