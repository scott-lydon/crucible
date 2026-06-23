from collections.abc import Callable

from shared.types import Transaction
from orchestrator.interfaces import Detector, Adversary, Oracle

# Composition root: this is the ONLY harness file allowed to import a victim
# from examples/. A victim gets plugged into the target-agnostic harness here.
from examples.targets.fraud_synth import (
    DETECTOR_THRESHOLD,
    V_THRESH,
    FlawedDetector,
    generate_batch,
    is_fraud,
)

from modules.red.mutator.mutator import AmountLoweringAdversary
from modules.oracles.held_out.oracle import HeldOutOracle
from modules.oracles.metamorphic.oracle import MetamorphicOracle
from modules.oracles.invariant.oracle import InvariantOracle
from modules.oracles.differential_stub.oracle import DifferentialStubOracle
from modules.oracles.llm_judge_mock.oracle import LlmJudgeMockOracle

# The victim's own decision threshold, surfaced for the harness composition
# layer (e.g. orchestrator.api) without that layer importing examples/.
DEFAULT_THRESHOLD: float = DETECTOR_THRESHOLD


def build_components(threshold: float = DETECTOR_THRESHOLD) -> dict[str, object]:
    detector: Detector = FlawedDetector()
    adversary: Adversary = AmountLoweringAdversary(
        score_fn=detector.score, label_fn=is_fraud, threshold=threshold
    )
    oracles: list[Oracle] = [
        HeldOutOracle(label_fn=is_fraud),
        MetamorphicOracle(label_fn=is_fraud),
        InvariantOracle(velocity_threshold=V_THRESH),
        DifferentialStubOracle(),
        LlmJudgeMockOracle(),
    ]
    label_fn: Callable[[Transaction], bool] = is_fraud
    return {
        "detector": detector,
        "adversary": adversary,
        "oracles": oracles,
        "label_fn": label_fn,
        "generate_fn": generate_batch,
    }
