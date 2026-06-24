"""Unit tests for the Option-B blue pillar — code-engineer + loop + validator.

All offline/deterministic with ZERO real LLM calls: a scripted mock provider
feeds the maker, a fake in-process sandbox executes the transform, an injected
fake retrain returns a detector that re-applies the transform. The sandbox-backed
tests live in ``test_sandbox_transform.py`` (gated on Docker). These prove the
maker parses, the loop ITERATES with feedback, and it HONESTLY FAILS — no real
LLM, no Docker.
"""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from modules.blue.code_engineer import (
    AttemptRecord,
    BlueCodeEngineer,
    EngineeredProposal,
)
from modules.blue.loop import _compile_engineer, run_blue_round
from modules.blue.validator import HoldoutValidator
from shared.llm.base import LLMResponse
from shared.sandbox.base import SandboxResult


# --- test doubles ----------------------------------------------------------


class _ScriptedProvider:
    """``LLMProvider`` that returns a fixed list of payloads, one per call."""

    def __init__(self, payloads: Sequence[str]) -> None:
        self._payloads = list(payloads)
        self.calls = 0

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        json_schema: Mapping[str, object] | None = None,
    ) -> LLMResponse:
        text = self._payloads[min(self.calls, len(self._payloads) - 1)]
        self.calls += 1
        return LLMResponse(
            text=text, model="mock", input_tokens=0, output_tokens=0, dollars=0.0
        )


class _InProcessSandbox:
    """A Sandbox that runs the wrapped transform locally (no Docker).

    Mirrors ``LocalDockerSandbox.run_python``'s contract: takes a code string,
    returns a ``SandboxResult``. Used only in unit tests; the real isolation
    boundary is exercised by the Docker-gated sandbox tests.
    """

    def run_python(
        self, code: str, *, timeout_s: float = 10.0, network: bool = False
    ) -> SandboxResult:
        import contextlib
        import io

        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                exec(code, {})  # noqa: S102 — wrapped harness code, test-only
        except Exception as exc:  # noqa: BLE001 — mimic a sandbox nonzero exit
            return SandboxResult(
                stdout=out.getvalue(), stderr=f"{type(exc).__name__}: {exc}",
                exit_code=1, job_id="test", timed_out=False,
            )
        return SandboxResult(
            stdout=out.getvalue(), stderr="", exit_code=0, job_id="test",
            timed_out=False,
        )


@dataclass
class _ReapplyDetector:
    """Scores by re-applying the engineer to a raw dict: night-hour -> caught."""

    engineer: Callable[[dict[str, object]], float]

    def score(self, sample: object) -> float:
        row = sample if isinstance(sample, dict) else vars(sample)
        return 0.9 if self.engineer(row) in (0.0, 1.0, 2.0, 3.0) else 0.1


def _fake_retrain(
    train_rows: Sequence[dict[str, object]],
    values: Sequence[float],
    engineer: Callable[[dict[str, object]], float],
) -> _ReapplyDetector:
    return _ReapplyDetector(engineer=engineer)


class _AmtOnlyDetector:
    """The old, blind detector: clears low-amount rows (the evasion target)."""

    def score(self, sample: object) -> float:
        row = sample if isinstance(sample, dict) else vars(sample)
        return 0.9 if float(row["amt"]) > 100 else 0.1


# A transform that does NOT recover (a daytime-hour constant the reapply
# detector ignores) vs one that DOES (extract the real night hour from raw).
_BAD_SRC = "return 50.0"
_HOUR_SRC = "return float(str(row['trans_date_trans_time'])[11:13])"
_BROKEN_SRC = "return row['does_not_exist'] + 1"

# Night-fraud holdout rows with amt LOWERED (the evasion). hour=1 (01:xx).
_HOLDOUT = [
    {"txn_index": i, "amt": 10.0, "trans_date_trans_time": "2019-01-01 01:30:00"}
    for i in range(5)
]
_TRAIN = [
    {"txn_index": i, "amt": 10.0, "trans_date_trans_time": "2019-01-01 01:30:00",
     "is_fraud": 1}
    for i in range(5)
]
_RAW_COLUMNS = ["trans_date_trans_time", "amt", "category"]
_BASE = ["amt", "cat_risk"]


def _is_night(sample: object) -> bool:
    row = sample if isinstance(sample, dict) else vars(sample)
    return str(row["trans_date_trans_time"])[11:13] in ("00", "01", "02", "03")


def _payload(name: str, src: str) -> str:
    return json.dumps({"feature_name": name, "rationale": f"try {name}", "engineer_src": src})


# --- code engineer ---------------------------------------------------------


def test_code_engineer_parses_proposal() -> None:
    provider = _ScriptedProvider([
        json.dumps({
            "feature_name": "hour",
            "rationale": "night-hour is the missed signal",
            "engineer_src": "return float(str(row['trans_date_trans_time'])[11:13])",
        })
    ])
    eng = BlueCodeEngineer(provider, max_iters=3, max_repairs=1)
    proposal = eng.propose(
        catalog_summary=[{"feature": "amt", "direction": "decrease", "count": 7}],
        base_features=_BASE,
        raw_columns=_RAW_COLUMNS,
        sample_rows=_TRAIN[:2],
        history=[],
    )
    assert isinstance(proposal, EngineeredProposal)
    assert proposal.feature_name == "hour"
    assert "trans_date_trans_time" in proposal.engineer_src
    assert eng.calls_made == 1


def test_code_engineer_fails_loud_on_malformed_output() -> None:
    provider = _ScriptedProvider(['{"feature_name": "x"}'])  # missing keys
    eng = BlueCodeEngineer(provider)
    try:
        eng.propose(
            catalog_summary=[], base_features=_BASE, raw_columns=_RAW_COLUMNS,
            sample_rows=[], history=[],
        )
    except ValueError as exc:
        assert "malformed" in str(exc) or "engineer_src" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError on malformed provider output")


def test_compile_engineer_runs_body() -> None:
    fn = _compile_engineer(_HOUR_SRC)
    assert fn({"trans_date_trans_time": "2019-01-01 01:30:00"}) == 1.0


# --- loop: iterates with feedback ------------------------------------------


def test_loop_iterates_and_recovers_on_second_attempt() -> None:
    # Attempt 1: a constant transform that does NOT recover. Attempt 2: the hour
    # transform that DOES. The loop must iterate, use feedback, and end recovered.
    provider = _ScriptedProvider([_payload("const", _BAD_SRC), _payload("hour", _HOUR_SRC)])
    eng = BlueCodeEngineer(provider, max_iters=3, max_repairs=0)
    result = run_blue_round(
        catalog=[{"feature": "amt", "direction": "decrease", "count": 7}],
        base_features=_BASE,
        raw_columns=_RAW_COLUMNS,
        train_rows=_TRAIN,
        holdout_rows=_HOLDOUT,
        sandbox=_InProcessSandbox(),
        engineer_agent=eng,
        retrain_engineered_fn=_fake_retrain,
        label_fn=_is_night,
        threshold=0.5,
        old_detector=_AmtOnlyDetector(),
    )
    assert len(result.iterations) == 2  # iterated: bad then good
    assert result.iterations[0].recovered == 0.0  # const did not recover
    assert result.iterations[0].sandbox_ok is True
    assert result.iterations[1].recovered > 0.0  # hour recovered
    assert result.feature_name == "hour"  # best iteration kept
    assert result.validation.recovered > 0.0
    assert result.new_detector is not None


def test_loop_honest_fail_when_no_attempt_recovers() -> None:
    # Every attempt is a non-recovering constant -> recovered==0, no exception.
    provider = _ScriptedProvider([_payload("c", _BAD_SRC)])
    eng = BlueCodeEngineer(provider, max_iters=3, max_repairs=0)
    result = run_blue_round(
        catalog=[],
        base_features=_BASE,
        raw_columns=_RAW_COLUMNS,
        train_rows=_TRAIN,
        holdout_rows=_HOLDOUT,
        sandbox=_InProcessSandbox(),
        engineer_agent=eng,
        retrain_engineered_fn=_fake_retrain,
        label_fn=_is_night,
        threshold=0.5,
        old_detector=_AmtOnlyDetector(),
    )
    assert len(result.iterations) == 3  # exhausted max_iters
    assert result.validation.recovered == 0.0  # HONEST FAIL, no rigged number
    assert all(it.recovered == 0.0 for it in result.iterations)


def test_loop_repairs_sandbox_error_then_recovers() -> None:
    # Attempt 1 proposes BROKEN code (sandbox error) -> repair feeds the error
    # back -> the repaired hour transform runs and recovers within one iteration.
    provider = _ScriptedProvider([
        _payload("hour", _BROKEN_SRC),   # initial: references a missing column
        _payload("hour", _HOUR_SRC),     # repair: fixed
    ])
    eng = BlueCodeEngineer(provider, max_iters=2, max_repairs=1)
    result = run_blue_round(
        catalog=[],
        base_features=_BASE,
        raw_columns=_RAW_COLUMNS,
        train_rows=_TRAIN,
        holdout_rows=_HOLDOUT,
        sandbox=_InProcessSandbox(),
        engineer_agent=eng,
        retrain_engineered_fn=_fake_retrain,
        label_fn=_is_night,
        threshold=0.5,
        old_detector=_AmtOnlyDetector(),
    )
    assert result.validation.recovered > 0.0  # repaired and recovered
    assert result.iterations[-1].sandbox_ok is True
    assert provider.calls == 2  # one propose + one repair


def test_loop_records_failed_iteration_when_repairs_exhausted() -> None:
    # Broken code with zero repairs -> the iteration is recorded as a sandbox
    # failure (sandbox_ok False, error captured), loop continues honestly.
    provider = _ScriptedProvider([_payload("hour", _BROKEN_SRC)])
    eng = BlueCodeEngineer(provider, max_iters=1, max_repairs=0)
    result = run_blue_round(
        catalog=[],
        base_features=_BASE,
        raw_columns=_RAW_COLUMNS,
        train_rows=_TRAIN,
        holdout_rows=_HOLDOUT,
        sandbox=_InProcessSandbox(),
        engineer_agent=eng,
        retrain_engineered_fn=_fake_retrain,
        label_fn=_is_night,
        threshold=0.5,
        old_detector=_AmtOnlyDetector(),
    )
    assert len(result.iterations) == 1
    assert result.iterations[0].sandbox_ok is False
    assert result.iterations[0].error is not None
    assert result.validation.recovered == 0.0
    assert result.new_detector is None


# --- validator (unchanged contract) ----------------------------------------


@dataclass(frozen=True)
class _Sample:
    txn_index: int
    amt: float
    hour: int


class _NightCatchingDetector:
    def score(self, sample: object) -> float:
        return 0.9 if getattr(sample, "hour") in (0, 1, 2) else 0.1


def _is_night_fraud(sample: object) -> bool:
    return getattr(sample, "hour") in (0, 1, 2)


def test_validator_computes_recovery() -> None:
    holdout = [_Sample(txn_index=i, amt=10.0, hour=1) for i in range(5)]
    result = HoldoutValidator().validate(
        new_detector=_NightCatchingDetector(),
        holdout_samples=holdout,
        label_fn=_is_night_fraud,
        threshold=0.5,
    )
    assert result.n == 5
    assert result.detection_after == 1.0
    assert result.recovered == 1.0


def test_validator_empty_holdout() -> None:
    result = HoldoutValidator().validate(
        new_detector=_NightCatchingDetector(),
        holdout_samples=[],
        label_fn=_is_night_fraud,
        threshold=0.5,
    )
    assert result == result.__class__(0.0, 0.0, 0.0, 0)


def test_attempt_record_shape() -> None:
    rec = AttemptRecord(
        rationale="r", feature_name="f", engineer_src="return 1.0",
        sandbox_error=None, detection_after=0.5, recovered=0.5,
    )
    assert rec.feature_name == "f"
