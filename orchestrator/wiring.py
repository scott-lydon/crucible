import pathlib
from collections.abc import Callable

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

from modules.red.mutator.mutator import MetamorphicEvasionAdversary
from modules.oracles.held_out.oracle import HeldOutOracle
from modules.oracles.metamorphic.oracle import MetamorphicOracle
from modules.oracles.invariant.oracle import InvariantOracle
from modules.oracles.differential_stub.oracle import DifferentialStubOracle
from modules.oracles.llm_judge_mock.oracle import LlmJudgeMockOracle

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
        DifferentialStubOracle(),
        LlmJudgeMockOracle(),
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
