"""White-box red adversary (US-14 / slice-12).

The black-box red agent probes the detector blind. The WHITE-BOX pass hands the
red agent the verifiers' own protocol descriptions (the verification scheme) so
it can craft an evasion that fools the detector AND the oracles, while staying
truly positive per the label oracle. The platform then measures its catch rate
against this informed attacker — the headline number is recall against an
informed adversary, never an ignorant one.

Per ``constitution.md`` §1 the white-box self-test pass runs on **Opus 4.8**
(the same tier as the judge oracle), bounded by a call budget; the composition
root injects the provider. The LLM search + every verification step is reused
from ``LlmRedAdversary`` (it never trusts the LLM's word — every proposal is
re-checked against the real ``score_fn``/``label_fn``), so this wrapper only
injects the scheme into the prompt and keeps a deterministic fallback.

Cannot beat the held-out ground truth by definition: a mutation the held-out
rule calls negative is not an evasion, so the informed attacker can only erode
the HEURISTIC oracles' contribution — never the ground-truth label authority.
"""

from collections.abc import Callable, Sequence

from orchestrator.interfaces import Adversary
from shared.llm.base import LLMProvider
from shared.types import SealedSpec

from modules.red.catalog import StrategyCatalog
from modules.red.llm_red.agent import LlmRedAdversary

_SCHEME_PREAMBLE = (
    "WHITE-BOX INFORMATION — you are ALSO being checked by these independent "
    "verifiers after the detector clears a sample. Craft an evasion that the "
    "DETECTOR and these verifiers all miss, while the transaction stays genuinely "
    "positive per the ground-truth label authority (you cannot fool that one — a "
    "sample it calls non-positive is not a valid evasion). The verifiers:\n"
)


def _prompt_suffix(scheme: str) -> str:
    return _SCHEME_PREAMBLE + scheme


class WhiteBoxRedAdversary:
    """LLM red search informed by the oracles' verification scheme.

    Implements the ``Adversary`` protocol. ``primary`` is an Opus-backed LLM red
    agent whose prompt carries the scheme; ``fallback`` (the free deterministic
    mutator) keeps the loop alive when the LLM finds nothing or its budget is
    spent — exactly like the black-box hybrid.
    """

    def __init__(
        self,
        provider: LLMProvider,
        spec: SealedSpec,
        score_fn: Callable[[object], float],
        label_fn: Callable[[object], bool],
        threshold: float,
        scheme: str,
        fallback: Adversary | None = None,
        *,
        movable_features: Sequence[str] | None = None,
        max_attempts: int = 3,
        max_calls: int | None = None,
        catalog: StrategyCatalog | None = None,
    ) -> None:
        self._primary = LlmRedAdversary(
            provider=provider,
            spec=spec,
            score_fn=score_fn,
            label_fn=label_fn,
            threshold=threshold,
            movable_features=movable_features,
            max_attempts=max_attempts,
            max_calls=max_calls,
            catalog=catalog,
            prompt_suffix=_prompt_suffix(scheme),
        )
        self._fallback = fallback

    @property
    def calls_made(self) -> int:
        return self._primary.calls_made

    def mutate(self, sample: object, score: float) -> object | None:
        result = self._primary.mutate(sample, score)
        if result is not None:
            return result
        # Live (fallback=None): the LLM drives every attack; a None result is an
        # honest "no evasion", not a scripted rescue. The deterministic fallback is
        # wired ONLY offline (white_box_max_calls == 0, the test path).
        if self._fallback is None:
            return None
        return self._fallback.mutate(sample, score)
