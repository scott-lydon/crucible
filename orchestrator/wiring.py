from collections.abc import Callable

from shared.types import Transaction
from orchestrator.interfaces import Detector, Adversary, Oracle
from modules.targets.fraud_detector.detector import FlawedDetector
from modules.targets.synth.rule import is_fraud
from modules.targets.synth.generator import generate_batch
from modules.red.mutator.mutator import AmountLoweringAdversary
from modules.oracles.held_out.oracle import HeldOutOracle
from modules.oracles.metamorphic.oracle import MetamorphicOracle
from modules.oracles.invariant.oracle import InvariantOracle
from modules.oracles.differential_stub.oracle import DifferentialStubOracle
from modules.oracles.llm_judge_mock.oracle import LlmJudgeMockOracle


def build_components(threshold: float) -> dict[str, object]:
    detector: Detector = FlawedDetector()
    adversary: Adversary = AmountLoweringAdversary(
        score_fn=detector.score, label_fn=is_fraud, threshold=threshold
    )
    oracles: list[Oracle] = [
        HeldOutOracle(),
        MetamorphicOracle(),
        InvariantOracle(),
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
