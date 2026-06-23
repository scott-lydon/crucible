import pathlib
from collections.abc import Callable, Sequence

from orchestrator.interfaces import Detector, Adversary, Oracle
from shared.types import SealedSpec, sealed_spec_from_yaml

# Composition root: this is the ONLY harness file allowed to import a victim
# from examples/. A victim gets plugged into the target-agnostic harness here.
from examples.targets.fraud_synth import (
    DETECTOR_THRESHOLD,
    FlawedDetector,
    generate_batch,
    is_fraud,
)
from examples.targets import fraud_sparkov

from modules.targets.local_model.adapter import LocalModelTarget
from modules.blue.proposer import BlueProposer
from modules.red.mutator.mutator import MetamorphicEvasionAdversary
from modules.red.llm_red.agent import LlmRedAdversary
from modules.red.hybrid.adversary import HybridAdversary
from modules.red.catalog import StrategyCatalog
from modules.oracles.held_out.oracle import HeldOutOracle
from modules.oracles.metamorphic.oracle import MetamorphicOracle
from modules.oracles.invariant.oracle import InvariantOracle
from modules.oracles.differential.oracle import DifferentialOracle
from modules.oracles.llm_judge.oracle import LlmJudgeOracle
from shared.llm import AnthropicApiProvider, MockProvider
from shared.llm.base import LLMProvider

# The victim's own decision threshold, surfaced for the harness composition
# layer (e.g. orchestrator.api) without that layer importing examples/.
DEFAULT_THRESHOLD: float = DETECTOR_THRESHOLD

# Repo-root-relative path to the victim's SealedSpec.
_SPEC_PATH = pathlib.Path(__file__).resolve().parent.parent / "specs" / "fraud_v0.yaml"


def _load_spec() -> SealedSpec:
    return sealed_spec_from_yaml(_SPEC_PATH.read_text())


def build_components(threshold: float = DETECTOR_THRESHOLD) -> dict[str, object]:
    spec = _load_spec()
    detector: Detector = FlawedDetector()
    adversary: Adversary = MetamorphicEvasionAdversary(
        score_fn=detector.score, label_fn=is_fraud, threshold=threshold, spec=spec
    )
    oracles: list[Oracle] = [
        HeldOutOracle(label_fn=is_fraud),
        MetamorphicOracle(label_fn=is_fraud),
        InvariantOracle(),
        # Synthetic victim ships no second-family model — the differential
        # oracle honestly ABSTAINS (weight 0), it is not a stub.
        DifferentialOracle(),
        # Synth UNIT-TEST victim: a deterministic MockProvider test double keeps
        # the synth fixture offline/free. This is honestly the test fixture, not
        # the product — the real Opus judge lives in build_components_sparkov.
        LlmJudgeOracle(provider=MockProvider(
            text='{"per_obligation": [], "independent_finding": "mock", '
                 '"vote": "fail", "reason": "mock"}')),
    ]
    label_fn: Callable[[object], bool] = is_fraud
    return {
        "detector": detector,
        "adversary": adversary,
        "oracles": oracles,
        "label_fn": label_fn,
        "generate_fn": generate_batch,
        "spec": spec,
    }


def build_components_sparkov(
    threshold: float = fraud_sparkov.DETECTOR_THRESHOLD,
    judge_provider: LLMProvider | None = None,
    judge_max_calls: int | None = 25,
    red_provider: LLMProvider | None = None,
    red_max_calls: int | None = 20,
    blue_provider: LLMProvider | None = None,
    blue_max_calls: int | None = 5,
) -> dict[str, object]:
    """Wire the REAL Sparkov victim into the target-agnostic harness.

    The flawed detector is the serialized LightGBM model loaded via the generic
    LocalModelTarget over the victim-declared proxy features (amt, cat_risk).
    All paths resolve from the victim module, so nothing here is environment-
    dependent. Ground truth + the SealedSpec come from the victim package.

    ``judge_provider`` defaults to the REAL Opus 4.8 provider (the demo path);
    tests inject a ``MockProvider`` to keep the loop offline/free.
    ``judge_max_calls`` caps the billed judge calls per run (plan §6): the demo
    makes at most 25 real Opus calls, then the judge abstains honestly.

    The adversary is a ``HybridAdversary``: a REAL Sonnet 4.6 LLM red agent
    (constitution §1: Sonnet on the inner red loop) first, the FREE deterministic
    metamorphic mutator as fallback. ``red_provider`` defaults to the real Sonnet
    provider (the demo path); tests inject a ``MockProvider`` (or set
    ``red_max_calls=0``) to keep the loop offline/free. ``red_max_calls`` caps
    the billed Sonnet calls per run: the demo makes at most 20 real Sonnet calls,
    after which the LLM agent returns None and the deterministic fallback drives
    the loop (bounding spend while keeping co-evolution alive).

    For the blue pillar this also returns ``retrain_fn`` (the victim's
    ``retrain_with_features`` wrapped to yield a generic ``LocalModelTarget`` over
    the new feature set), ``available_features``/``current_features``, and a
    ``BlueProposer`` (real Sonnet 4.6 by default per constitution §1, capped by
    ``blue_max_calls``; tests inject a ``MockProvider`` or set ``blue_max_calls=0``
    to use the deterministic fallback).
    """
    spec = fraud_sparkov.load_spec()
    detector: Detector = LocalModelTarget(
        model_path=fraud_sparkov.MODEL_PATH,
        feature_names=fraud_sparkov.DETECTOR_FEATURES,
    )
    sparkov_is_fraud: Callable[[object], bool] = fraud_sparkov.is_fraud
    catalog = StrategyCatalog()
    llm_red = LlmRedAdversary(
        provider=red_provider
        if red_provider is not None
        else AnthropicApiProvider(model="claude-sonnet-4-6"),
        spec=spec,
        score_fn=detector.score,
        label_fn=sparkov_is_fraud,
        threshold=threshold,
        max_calls=red_max_calls,
        catalog=catalog,
    )
    deterministic = MetamorphicEvasionAdversary(
        score_fn=detector.score,
        label_fn=sparkov_is_fraud,
        threshold=threshold,
        spec=spec,
    )
    adversary: Adversary = HybridAdversary(primary=llm_red, fallback=deterministic)
    oracles: list[Oracle] = [
        HeldOutOracle(label_fn=sparkov_is_fraud),
        MetamorphicOracle(label_fn=sparkov_is_fraud),
        InvariantOracle(),
        # REAL cross-family second opinion: an unsupervised sklearn
        # IsolationForest (different family from the LightGBM target) trained
        # on the real Sparkov data over a richer feature set that includes the
        # night `hour` the amt-reliant target ignores.
        DifferentialOracle(second_opinion_is_fraud=fraud_sparkov.isoforest_is_fraud),
        # REAL Opus 4.8 judge (constitution §1: Opus on the judge). Live provider
        # by default, nothing mocked in the demo path; budgeted to bound spend.
        LlmJudgeOracle(
            provider=judge_provider
            if judge_provider is not None
            else AnthropicApiProvider(model="claude-opus-4-8"),
            max_calls=judge_max_calls,
        ),
    ]
    # Blue pillar: the victim's retrain capability, wrapped so the harness gets
    # back a generic Detector (LocalModelTarget) over the new feature ORDER. The
    # harness never imports the victim's retrainer — it is injected here, at the
    # one composition root permitted to see examples/.
    def retrain_fn(feature_names: Sequence[str]) -> Detector:
        path = fraud_sparkov.retrain_with_features(list(feature_names))
        return LocalModelTarget(model_path=path, feature_names=list(feature_names))

    blue_proposer = BlueProposer(
        provider=blue_provider
        if blue_provider is not None
        else AnthropicApiProvider(model="claude-sonnet-4-6"),
        max_calls=blue_max_calls,
    )

    return {
        "detector": detector,
        "adversary": adversary,
        "oracles": oracles,
        "label_fn": sparkov_is_fraud,
        "generate_fn": fraud_sparkov.generate_batch,
        "spec": spec,
        "catalog": catalog,
        "retrain_fn": retrain_fn,
        "available_features": list(fraud_sparkov.AVAILABLE_FEATURES),
        "current_features": list(fraud_sparkov.DETECTOR_FEATURES),
        "blue_proposer": blue_proposer,
    }
