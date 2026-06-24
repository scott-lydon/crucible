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
    synth_strategy,
)
from examples.targets import fraud_sparkov

from modules.targets.local_model.adapter import LocalModelTarget
from modules.blue.code_engineer import BlueCodeEngineer
from modules.red.mutator.mutator import MetamorphicEvasionAdversary
from modules.red.llm_red.agent import LlmRedAdversary
from modules.red.hybrid.adversary import HybridAdversary
from modules.red.white_box import WhiteBoxRedAdversary
from modules.red.catalog import StrategyCatalog
from modules.oracles.scheme import verification_scheme
from modules.oracles.held_out.oracle import HeldOutOracle
from modules.oracles.metamorphic.oracle import MetamorphicOracle
from modules.oracles.invariant.oracle import InvariantOracle
from modules.oracles.differential.oracle import DifferentialOracle
from modules.oracles.property_fuzz.oracle import PropertyFuzzOracle
from modules.oracles.llm_judge.oracle import LlmJudgeOracle
from shared.llm import AnthropicApiProvider, MockProvider, PersistingLLMProvider
from shared.llm.base import LLMProvider
from shared.sandbox import LocalDockerSandbox

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# The victim's own decision threshold, surfaced for the harness composition
# layer (e.g. orchestrator.api) without that layer importing examples/.
DEFAULT_THRESHOLD: float = DETECTOR_THRESHOLD

# Repo-root-relative path to the victim's SealedSpec.
_SPEC_PATH = pathlib.Path(__file__).resolve().parent.parent / "specs" / "fraud_v0.yaml"


def _load_spec() -> SealedSpec:
    return sealed_spec_from_yaml(_SPEC_PATH.read_text())


# --- Target registry (US-1 input side) -------------------------------------
# The composition root is the one place allowed to see ``examples/``, so it is
# also the single source of truth for which bundled example targets exist, their
# model-artifact references, and their DEFAULT sealed-spec YAML. The API layer
# (orchestrator.targets_registry) reads THIS — it never imports ``examples`` —
# so the launcher's target list + spec pre-fill come from the same place the run
# is actually wired from. No hardcoded frontend list, no duplicated YAML.


def target_registry() -> dict[str, dict[str, object]]:
    """The bundled example targets, keyed by name.

    Each value: ``{kind, model_artifact_ref, has_default_spec, default_spec_yaml}``.
    ``model_artifact_ref`` is informational/read-only (uploading a custom model or
    code is out of scope, spec.md §4). ``default_spec_yaml`` is the SAME spec text
    ``build_components``/``build_components_sparkov`` load by default.
    """
    return {
        "sparkov": {
            "kind": fraud_sparkov.load_spec().target_kind,
            # The serialized LightGBM victim the LocalModelTarget loads.
            "model_artifact_ref": f"local:{fraud_sparkov.MODEL_PATH.name}",
            "has_default_spec": True,
            "default_spec_yaml": fraud_sparkov.SPEC_PATH.read_text(),
        },
        "synth": {
            "kind": _load_spec().target_kind,
            # A coded in-process detector, not a serialized artifact — surfaced
            # honestly rather than faking a file reference.
            "model_artifact_ref": "in-process:FlawedDetector (synthetic, no artifact)",
            "has_default_spec": True,
            "default_spec_yaml": _SPEC_PATH.read_text(),
        },
    }


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
        # Generative invariant-counterexample search (Hypothesis, no LLM):
        # searches Transaction-space for an input that satisfies a declared
        # must_flag_when invariant yet the detector clears. Seeded/deterministic.
        PropertyFuzzOracle(
            score_fn=detector.score,
            strategy=synth_strategy(),
            max_examples=100,
            seed=8,
        ),
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
    white_box_provider: LLMProvider | None = None,
    white_box_max_calls: int | None = 15,
    blue_provider: LLMProvider | None = None,
    blue_max_iters: int = 3,
    blue_max_repairs: int = 1,
    blue_sandbox: object | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    run_id: str | None = None,
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

    For the blue pillar this wires Option B — a genuine code-engineering maker:
    a ``BlueCodeEngineer`` that gets ONLY the RAW data surface (no derived menu)
    and writes a feature-engineering transform, the locked-down
    ``LocalDockerSandbox`` that runs that untrusted code, the victim's
    ``load_raw_rows``/``load_holdout_raw_rows`` raw rows, ``retrain_with_engineered``
    (base features + the engineered column), and the base feature names. The maker
    uses REAL Opus 4.8 by default.

    DEVIATION FROM CONSTITUTION §1: §1 puts Sonnet 4.6 on the inner blue loop, but
    blue here generates CODE (a feature-engineering transform run in the sandbox),
    so it is held to the higher Opus tier per the operator's documented preference
    (see ``constitution.md`` §1 deviation note and ``CLAUDE.md`` "Opus everywhere"
    BUILD-TIME scope — this RUNTIME use of Opus for blue codegen is the explicit,
    narrow exception). Tests inject a deterministic mock provider + an in-process
    sandbox so the suite makes ZERO real LLM calls. The maker is bounded
    (``blue_max_iters``/``blue_max_repairs``) and ALLOWED TO FAIL — no guaranteed
    recovery.
    """
    spec = fraud_sparkov.load_spec()

    def _wrap(inner: LLMProvider, pillar: str) -> LLMProvider:
        """Record every call this provider makes to ``llm_calls`` (US-2/3/10).

        Only wraps when a ``session_factory`` and ``run_id`` are threaded in (the
        run path). Without them the raw provider is returned unchanged so unit
        construction stays side-effect free. The decorator makes NO extra call.
        """
        if session_factory is None or run_id is None:
            return inner
        return PersistingLLMProvider(
            inner=inner,
            session_factory=session_factory,
            run_id=run_id,
            pillar=pillar,
        )

    detector: Detector = LocalModelTarget(
        model_path=fraud_sparkov.MODEL_PATH,
        feature_names=fraud_sparkov.DETECTOR_FEATURES,
    )
    sparkov_is_fraud: Callable[[object], bool] = fraud_sparkov.is_fraud
    catalog = StrategyCatalog()
    llm_red = LlmRedAdversary(
        provider=_wrap(
            red_provider
            if red_provider is not None
            else AnthropicApiProvider(model="claude-sonnet-4-6"),
            "red",
        ),
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
    # WHITE-BOX red (US-14): an Opus 4.8 LLM red agent (constitution §1: the
    # white-box self-test pass runs on the higher tier) whose prompt carries the
    # oracles' verification scheme, with the SAME free deterministic fallback.
    # Budgeted independently of the Sonnet black-box loop. Tests inject a
    # MockProvider / white_box_max_calls=0 so the suite makes ZERO real calls.
    white_box_deterministic = MetamorphicEvasionAdversary(
        score_fn=detector.score,
        label_fn=sparkov_is_fraud,
        threshold=threshold,
        spec=spec,
    )
    oracles: list[Oracle] = [
        HeldOutOracle(label_fn=sparkov_is_fraud),
        MetamorphicOracle(label_fn=sparkov_is_fraud),
        InvariantOracle(),
        # REAL cross-family second opinion: an unsupervised sklearn
        # IsolationForest (different family from the LightGBM target) trained
        # on the real Sparkov data over a richer feature set that includes the
        # night `hour` the amt-reliant target ignores.
        DifferentialOracle(second_opinion_is_fraud=fraud_sparkov.isoforest_is_fraud),
        # Generative invariant-counterexample search (Hypothesis, ZERO LLM calls):
        # generatively searches SparkovTxn-space for an input that satisfies a
        # declared must_flag_when invariant yet the amt-reliant detector clears.
        # Seeded => deterministic; run-level probe surfaced per verdict.
        PropertyFuzzOracle(
            score_fn=detector.score,
            strategy=fraud_sparkov.sparkov_strategy(),
            max_examples=200,
            seed=8,
        ),
        # REAL Opus 4.8 judge (constitution §1: Opus on the judge). Live provider
        # by default, nothing mocked in the demo path; budgeted to bound spend.
        LlmJudgeOracle(
            provider=_wrap(
                judge_provider
                if judge_provider is not None
                else AnthropicApiProvider(model="claude-opus-4-8"),
                "judge",
            ),
            max_calls=judge_max_calls,
        ),
    ]
    # Blue pillar (Option B): the victim's RAW surface + engineered-retrain
    # capability, injected here at the one composition root permitted to see
    # examples/. The harness never imports the victim — it only sees a generic
    # Detector and plain raw-row dicts.
    def retrain_engineered_fn(
        train_rows: Sequence[dict[str, object]],
        engineered_values: Sequence[float],
        engineer: Callable[[dict[str, object]], float],
    ) -> Detector:
        return fraud_sparkov.retrain_with_engineered(
            list(train_rows),
            list(engineered_values),
            list(fraud_sparkov.BASE_FEATURES),
            engineer,
        )

    blue_engineer = BlueCodeEngineer(
        provider=_wrap(
            blue_provider
            if blue_provider is not None
            # Opus 4.8 for blue CODE generation (documented §1 deviation; see docstring).
            else AnthropicApiProvider(model="claude-opus-4-8"),
            "blue",
        ),
        max_iters=blue_max_iters,
        max_repairs=blue_max_repairs,
    )
    sandbox = blue_sandbox if blue_sandbox is not None else LocalDockerSandbox()

    # Assemble the verification scheme from the live oracles (Targets-and-Oracles
    # owns describe()/assembly) and wire the white-box red pass against it.
    scheme = verification_scheme(oracles)
    white_box_adversary: Adversary = WhiteBoxRedAdversary(
        provider=_wrap(
            white_box_provider
            if white_box_provider is not None
            else AnthropicApiProvider(model="claude-opus-4-8"),
            "white_box",
        ),
        spec=spec,
        score_fn=detector.score,
        label_fn=sparkov_is_fraud,
        threshold=threshold,
        scheme=scheme,
        fallback=white_box_deterministic,
        max_calls=white_box_max_calls,
        catalog=catalog,
    )

    return {
        "detector": detector,
        "adversary": adversary,
        "white_box_adversary": white_box_adversary,
        "verification_scheme": scheme,
        "oracles": oracles,
        "label_fn": sparkov_is_fraud,
        "generate_fn": fraud_sparkov.generate_batch,
        "spec": spec,
        "catalog": catalog,
        "retrain_engineered_fn": retrain_engineered_fn,
        "load_raw_rows": fraud_sparkov.load_raw_rows,
        "load_holdout_raw_rows": fraud_sparkov.load_holdout_raw_rows,
        "base_features": list(fraud_sparkov.BASE_FEATURES),
        "raw_columns": list(fraud_sparkov.RAW_COLUMNS),
        "blue_engineer": blue_engineer,
        "blue_sandbox": sandbox,
        # The raw holdout has no derived `hour`, so the derived `is_fraud` rule
        # cannot read it — the maker validates against the REAL committed label.
        "raw_label_fn": fraud_sparkov.raw_is_fraud,
    }
