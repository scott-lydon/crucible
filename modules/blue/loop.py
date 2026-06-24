"""Blue round orchestration (Option B) — a genuine code-engineering maker.

The blue maker is NOT handed an answer menu. It gets only the RAW data surface
and must DISCOVER the missing signal, WRITE a feature-engineering transform, have
the harness sandbox-run that untrusted code, retrain, and measure recovery — then
ITERATE with feedback. It is ALLOWED TO FAIL: there is no guaranteed recovery.

Per iteration (bounded by ``engineer.max_iters``):

1. ``engineer.propose(history)`` -> ``{feature_name, rationale, engineer_src}``
   (the BODY of ``def engineer(row) -> float`` over the raw columns).
2. ``run_transform_in_sandbox`` over the bounded raw training sample. On a
   ``TransformError`` the maker may REPAIR (bounded by ``engineer.max_repairs``),
   feeding the error back; if repairs are exhausted the iteration is recorded as
   a failure and the loop continues with a fresh hypothesis.
3. Sandbox the transform over the holdout too (same vetted code, same schema),
   then ``retrain_engineered_fn(train_rows, train_values, engineer)`` -> a new
   detector that re-applies the transform at scoring time.
4. Validate recovery on the holdout (``detection_after`` vs ``detection_before``).
5. Record the iteration; ``recovered > min_recovery`` -> break (success).

Returns a :class:`BlueResult` with the BEST iteration plus the FULL trail.
``recovered`` may be ``0`` after all iters — an HONEST FAIL, not a rigged number.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from orchestrator.interfaces import Detector
from modules.blue.code_engineer import (
    AttemptRecord,
    BlueCodeEngineer,
    EngineeredProposal,
)
from modules.blue.sandbox_transform import (
    TransformError,
    run_transform_in_sandbox,
)
from modules.blue.validator import HoldoutValidator, ValidationResult
from shared.sandbox.base import Sandbox

# A trusted, in-process callable built from the vetted engineer_src, used to
# rebuild the engineered feature at scoring time inside the new detector.
EngineerFn = Callable[[dict[str, object]], float]
# Injected victim retrain: (train_rows, engineered_values, engineer) -> Detector.
RetrainEngineeredFn = Callable[
    [Sequence[dict[str, object]], Sequence[float], EngineerFn], Detector
]


@dataclass(frozen=True, slots=True)
class BlueIteration:
    """One propose->sandbox->retrain->validate attempt within a blue round."""

    rationale: str
    feature_name: str
    engineer_src: str
    sandbox_ok: bool
    error: str | None
    detection_after: float
    recovered: float


@dataclass(frozen=True, slots=True)
class BlueResult:
    """The outcome of one blue round: the BEST iteration plus the full trail.

    ``recovered`` may be ``0`` (honest fail). ``new_detector`` is ``None`` when no
    iteration produced a runnable transform at all.
    """

    rationale: str
    feature_name: str
    engineer_src: str
    new_detector: Detector | None
    validation: ValidationResult
    iterations: list[BlueIteration] = field(default_factory=list)


def _compile_engineer(engineer_src: str) -> EngineerFn:
    """Compile the vetted ``engineer`` body into a trusted in-process callable.

    The body already passed the Docker sandbox during discovery; the harness owns
    its re-execution at scoring time so the new detector can recompute the
    engineered feature on each holdout sample. Same boilerplate as the sandbox
    wrapper (``def engineer(row): <body>``).
    """
    indented = "\n".join(
        "    " + line if line.strip() else line for line in engineer_src.splitlines()
    )
    namespace: dict[str, object] = {}
    exec(f"def engineer(row):\n{indented}\n", namespace)  # noqa: S102
    fn = namespace["engineer"]

    def _call(row: dict[str, object]) -> float:
        return float(fn(row))  # type: ignore[operator]

    return _call


def _empty_validation() -> ValidationResult:
    return ValidationResult(
        detection_before=0.0, detection_after=0.0, recovered=0.0, n=0
    )


def run_blue_round(
    *,
    catalog: object,
    base_features: Sequence[str],
    raw_columns: Sequence[str],
    train_rows: Sequence[dict[str, object]],
    holdout_rows: Sequence[object],
    sandbox: Sandbox,
    engineer_agent: BlueCodeEngineer,
    retrain_engineered_fn: RetrainEngineeredFn,
    label_fn: Callable[[object], bool],
    threshold: float,
    old_detector: Detector | None = None,
    validator: HoldoutValidator | None = None,
    min_recovery: float = 0.0,
    sample_n: int = 3,
    vet_n: int = 500,
) -> BlueResult:
    """Run the bounded, iterate-with-feedback code-engineering blue round.

    The maker discovers a transform from the raw surface, the harness sandbox-runs
    it, retrains, and measures recovery. Iterates up to ``engineer_agent.max_iters``
    times, repairs sandbox errors up to ``engineer_agent.max_repairs`` per
    iteration, and stops early once ``recovered > min_recovery``. Returns the BEST
    iteration; recovery is NOT guaranteed.
    """
    catalog_summary = _catalog_summary(catalog)
    validator = validator if validator is not None else HoldoutValidator()
    train_list = list(train_rows)
    sample_rows = [dict(r) for r in train_list[:sample_n]]
    # The sandbox VET sample: a bounded prefix the untrusted transform runs over
    # to prove it executes safely and returns numeric output. The real retrain
    # then applies the now-trusted transform in-process over the FULL train set.
    vet_rows = [dict(r) for r in train_list[:vet_n]]

    iterations: list[BlueIteration] = []
    history: list[AttemptRecord] = []
    best_validation = _empty_validation()
    best_detector: Detector | None = None
    best = BlueResult(
        rationale="",
        feature_name="",
        engineer_src="",
        new_detector=None,
        validation=best_validation,
        iterations=iterations,
    )

    for _ in range(engineer_agent.max_iters):
        proposal = engineer_agent.propose(
            catalog_summary=catalog_summary,
            base_features=base_features,
            raw_columns=raw_columns,
            sample_rows=sample_rows,
            history=history,
        )

        # VET the transform in the sandbox over a BOUNDED sample (untrusted-
        # execution gate), repairing on error. The repair loop may replace the
        # proposal; it returns the one that ran.
        vet_values, last_error, proposal = _sandbox_with_repair(
            sandbox=sandbox,
            engineer_agent=engineer_agent,
            proposal=proposal,
            vet_rows=vet_rows,
            catalog_summary=catalog_summary,
            base_features=base_features,
            raw_columns=raw_columns,
            sample_rows=sample_rows,
            history=history,
        )

        if vet_values is None:
            iterations.append(
                BlueIteration(
                    rationale=proposal.rationale,
                    feature_name=proposal.feature_name,
                    engineer_src=proposal.engineer_src,
                    sandbox_ok=False,
                    error=last_error,
                    detection_after=0.0,
                    recovered=0.0,
                )
            )
            history.append(
                AttemptRecord(
                    rationale=proposal.rationale,
                    feature_name=proposal.feature_name,
                    engineer_src=proposal.engineer_src,
                    sandbox_error=last_error,
                    detection_after=None,
                    recovered=None,
                )
            )
            continue

        # Vetted in the sandbox: build the trusted in-process engineer and apply
        # it over the FULL training set (the sandbox was the safety gate; the
        # harness owns the now-trusted re-execution for the real retrain).
        engineer = _compile_engineer(proposal.engineer_src)
        train_values = [engineer(dict(r)) for r in train_list]
        detector = retrain_engineered_fn(train_list, train_values, engineer)
        validation = validator.validate(
            detector, holdout_rows, label_fn, threshold, old_detector=old_detector
        )
        iterations.append(
            BlueIteration(
                rationale=proposal.rationale,
                feature_name=proposal.feature_name,
                engineer_src=proposal.engineer_src,
                sandbox_ok=True,
                error=None,
                detection_after=validation.detection_after,
                recovered=validation.recovered,
            )
        )
        history.append(
            AttemptRecord(
                rationale=proposal.rationale,
                feature_name=proposal.feature_name,
                engineer_src=proposal.engineer_src,
                sandbox_error=None,
                detection_after=validation.detection_after,
                recovered=validation.recovered,
            )
        )
        if validation.recovered > best_validation.recovered:
            best_validation = validation
            best_detector = detector
            best = BlueResult(
                rationale=proposal.rationale,
                feature_name=proposal.feature_name,
                engineer_src=proposal.engineer_src,
                new_detector=detector,
                validation=validation,
                iterations=iterations,
            )
        if validation.recovered > min_recovery:
            break

    # Ensure the returned result reflects the full trail even on honest fail.
    return BlueResult(
        rationale=best.rationale,
        feature_name=best.feature_name,
        engineer_src=best.engineer_src,
        new_detector=best_detector,
        validation=best_validation,
        iterations=iterations,
    )


def _sandbox_with_repair(
    *,
    sandbox: Sandbox,
    engineer_agent: BlueCodeEngineer,
    proposal: EngineeredProposal,
    vet_rows: list[dict[str, object]],
    catalog_summary: Sequence[Mapping[str, object]],
    base_features: Sequence[str],
    raw_columns: Sequence[str],
    sample_rows: Sequence[Mapping[str, object]],
    history: Sequence[AttemptRecord],
) -> tuple[list[float] | None, str | None, EngineeredProposal]:
    """Run the transform; on ``TransformError`` ask the maker to repair (bounded).

    Returns ``(values, None, proposal)`` on success or ``(None, error, proposal)``
    once the bounded repairs are exhausted. The returned proposal is the one that
    actually ran last, so the caller records the code it tried.
    """
    current = proposal
    last_error: str | None = None
    for repair in range(engineer_agent.max_repairs + 1):
        outcome = run_transform_in_sandbox(sandbox, current.engineer_src, vet_rows)
        if not isinstance(outcome, TransformError):
            return outcome, None, current
        last_error = outcome.message
        if repair >= engineer_agent.max_repairs:
            break
        # Feed the sandbox error back and let the maker repair this iteration.
        repair_history = [
            *history,
            AttemptRecord(
                rationale=current.rationale,
                feature_name=current.feature_name,
                engineer_src=current.engineer_src,
                sandbox_error=last_error,
                detection_after=None,
                recovered=None,
            ),
        ]
        current = engineer_agent.propose(
            catalog_summary=catalog_summary,
            base_features=base_features,
            raw_columns=raw_columns,
            sample_rows=sample_rows,
            history=repair_history,
        )
    return None, last_error, current


def _catalog_summary(catalog: object) -> list[dict[str, object]]:
    """Read a catalog's ``summary()`` if present; tolerate a plain list/None."""
    if catalog is None:
        return []
    summary = getattr(catalog, "summary", None)
    if callable(summary):
        return list(summary())
    if isinstance(catalog, list):
        return catalog
    return []
