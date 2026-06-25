"""The DEMO test — the red -> blue -> recover arc on REAL Sparkov data (Option B).

ZERO real LLM calls: the red loop runs on its FREE deterministic fallback (Sonnet
budget 0, mock judge budget 0) and the blue maker is a scripted mock provider that
returns the BODY of an ``engineer`` extracting the night ``hour`` from the raw
``trans_date_trans_time`` column. The transform is run in an IN-PROCESS sandbox
(the Docker boundary is exercised separately in the gated sandbox tests); the
detector, the data, and the engineered retraining are all REAL.

Arc:
1. Run the real red loop -> the amt-lowering adversary lands evasions on the
   amt-reliant LightGBM detector (proof the gap exists).
2. run_blue_round over the victim's RAW surface -> the maker DISCOVERS the night
   hour, the harness sandbox-runs the transform, retrains a NEW LightGBM on the
   base features + the engineered hour, validates on the RAW held-out evasions.
3. ASSERT detection_after > detection_before AND materially > 0: the retrained
   model genuinely catches the amt-lowered night-fraud evasions the old model
   missed, from a transform the maker WROTE — not picked off a menu.

Skips (not fails) when the external CSVs / artifact are absent.
"""

import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from orchestrator.interfaces import Adversary, Detector, Oracle
from orchestrator.loop import run_loop
from orchestrator.wiring import build_components_sparkov
from shared.llm.base import LLMResponse
from shared.persistence import create_all, make_engine, make_session_factory
from shared.persistence.models import RunRow
from shared.sandbox.base import Sandbox, SandboxResult
from shared.types import SealedSpec

from examples.targets import fraud_sparkov
from modules.blue import BlueCodeEngineer, run_blue_round
from shared.llm import MockProvider

_THRESHOLD = 0.5
_N_ROUNDS = 4
_BATCH_SIZE = 400
_SEED = "sparkov-blue-recovery"

_DATA_READY = (
    fraud_sparkov.constants.TEST_CSV.exists()
    and fraud_sparkov.constants.TRAIN_CSV.exists()
    and fraud_sparkov.MODEL_PATH.exists()
    and fraud_sparkov.constants.CHECKSUM_PATH.exists()
)
_SKIP_REASON = (
    "Sparkov real CSVs / trained artifact missing (gitignored external inputs); "
    "run `python -m examples.targets.fraud_sparkov.train` after placing the data."
)

# The maker's engineered feature: the night hour, extracted from the raw
# timestamp. This is the BODY of `def engineer(row): ...` — code the maker WROTE,
# reasoning from the raw schema, not a feature picked off an answer menu.
_HOUR_SRC = "return float(str(row['trans_date_trans_time'])[11:13])"


class _ScriptedProvider:
    """Returns the maker's hour transform on its single call (zero real LLM)."""

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        json_schema: Mapping[str, object] | None = None,
    ) -> LLMResponse:
        text = json.dumps({
            "feature_name": "night_hour",
            "rationale": "extract the hour from the raw timestamp",
            "engineer_src": _HOUR_SRC,
        })
        return LLMResponse(text=text, model="mock", input_tokens=0, output_tokens=0, dollars=0.0)


class _InProcessSandbox:
    """Runs the wrapped transform locally (the Docker boundary is gated elsewhere)."""

    def run_python(
        self,
        code: str,
        *,
        timeout_s: float = 10.0,
        network: bool = False,
        stdin: str | None = None,
    ) -> SandboxResult:
        import contextlib
        import io
        import sys

        out = io.StringIO()
        saved_stdin = sys.stdin
        sys.stdin = io.StringIO(stdin or "")
        try:
            with contextlib.redirect_stdout(out):
                exec(code, {})  # noqa: S102 — wrapped harness code, test-only
        except Exception as exc:  # noqa: BLE001
            return SandboxResult(
                stdout=out.getvalue(), stderr=f"{type(exc).__name__}: {exc}",
                exit_code=1, job_id="t", timed_out=False,
            )
        finally:
            sys.stdin = saved_stdin
        return SandboxResult(
            stdout=out.getvalue(), stderr="", exit_code=0, job_id="t", timed_out=False,
        )


@pytest.fixture
async def sf() -> async_sessionmaker[AsyncSession]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    return make_session_factory(engine)


@pytest.mark.skipif(not _DATA_READY, reason=_SKIP_REASON)
async def test_blue_recovers_on_real_evasions(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    # Build with every LLM seam neutralized + an in-process sandbox: ZERO real
    # Sonnet/Opus calls, no Docker.
    comp = build_components_sparkov(
        threshold=_THRESHOLD,
        judge_provider=MockProvider(
            text='{"per_obligation":[],"independent_finding":"fixture",'
                 '"vote":"pass","reason":"fixture"}'),
        judge_max_calls=0,
        red_provider=MockProvider(text='{"feature":"amt","new_value":1.0,"rationale":"x"}'),
        red_max_calls=0,
        blue_provider=_ScriptedProvider(),
        blue_sandbox=_InProcessSandbox(),
    )
    detector = cast(Detector, comp["detector"])
    label_fn = cast(Callable[[object], bool], comp["label_fn"])
    raw_label_fn = cast(Callable[[object], bool], comp["raw_label_fn"])

    # --- 1. run the real red loop to produce successful evasions ----------
    run_id = str(uuid.uuid4())
    async with sf() as s:
        s.add(
            RunRow(
                id=run_id, seed=_SEED, status="pending", n_rounds=_N_ROUNDS,
                batch_size=_BATCH_SIZE, threshold=_THRESHOLD, params_json={},
            )
        )
        await s.commit()

    await run_loop(
        sf,
        run_id=run_id,
        seed=_SEED,
        n_rounds=_N_ROUNDS,
        batch_size=_BATCH_SIZE,
        threshold=_THRESHOLD,
        detector=detector,
        adversary=cast(Adversary, comp["adversary"]),
        oracles=cast(Sequence[Oracle], comp["oracles"]),
        label_fn=label_fn,
        generate_fn=cast(Callable[[str, int], list[object]], comp["generate_fn"]),
        spec=cast(SealedSpec, comp["spec"]),
    )

    # --- 2. the RAW data surface for the maker ----------------------------
    load_raw = cast(Callable[..., list[dict[str, object]]], comp["load_raw_rows"])
    load_holdout = cast(Callable[..., list[object]], comp["load_holdout_raw_rows"])
    train_rows = load_raw(limit=None)  # FULL data — the sparse fraud signal
    holdout_rows = load_holdout(limit=200, seed=0)
    assert holdout_rows, "no raw holdout evasions available"

    # The raw holdout carries NO derived `hour` — the maker must engineer it.
    assert not hasattr(holdout_rows[0], "hour")
    assert hasattr(holdout_rows[0], "trans_date_trans_time")

    # A genuine evasion holdout = only the amt-lowered night-frauds the OLD
    # amt-reliant detector actually CLEARS (most of them at the 0.5 evade factor).
    holdout_rows = [r for r in holdout_rows if detector.score(r) < _THRESHOLD]
    assert len(holdout_rows) > 100, len(holdout_rows)
    old_cleared = sum(1 for r in holdout_rows if detector.score(r) < _THRESHOLD)
    assert old_cleared == len(holdout_rows), (old_cleared, len(holdout_rows))

    # --- 3. run the real Option-B blue round (mock maker, REAL retrain) ----
    result = run_blue_round(
        catalog=comp["catalog"],
        base_features=cast(Sequence[str], comp["base_features"]),
        raw_columns=cast(Sequence[str], comp["raw_columns"]),
        train_rows=train_rows,
        holdout_rows=holdout_rows,
        sandbox=cast(Sandbox, comp["blue_sandbox"]),
        engineer_agent=cast(BlueCodeEngineer, comp["blue_engineer"]),
        retrain_engineered_fn=cast(Callable[..., Detector], comp["retrain_engineered_fn"]),
        label_fn=raw_label_fn,
        threshold=_THRESHOLD,
        old_detector=detector,
    )

    v = result.validation
    # --- 4. assert honest recovery from a maker-WRITTEN transform ----------
    assert v.n == len(holdout_rows)
    assert v.detection_before == pytest.approx(0.0, abs=1e-9), v.detection_before
    assert v.detection_after > v.detection_before, (v.detection_before, v.detection_after)
    # Honest, bounded recovery: a single engineered night-hour feature catches a
    # real share of the amt-lowered night-fraud evasions the old model cleared —
    # not a rigged 100%; amt still dominates the model (see raw_surface.py).
    assert v.detection_after > 0.15, v.detection_after
    assert result.new_detector is not None
    assert "trans_date_trans_time" in result.engineer_src  # the maker's own code
    assert len(result.iterations) >= 1

    print("\nBlue (Option B) recovery on REAL Sparkov evasions:")
    print(f"  holdout evasions (n)   = {v.n}")
    print(f"  engineered feature     = {result.feature_name}")
    print(f"  engineer_src           = {result.engineer_src!r}")
    print(f"  detection_before       = {v.detection_before:.3f}")
    print(f"  detection_after        = {v.detection_after:.3f}")
    print(f"  recovered              = {v.recovered:.3f}")
    print(f"  iterations             = {len(result.iterations)}")
