"""End-to-end red loop against the REAL Sparkov victim.

Loads a deterministic balanced batch of real records, runs the co-evolution
loop for several rounds against a fresh in-memory SQLite, and asserts the
HONEST story holds: as the amt-lowering adversary attacks the amount-reliant
flawed detector, holdout detection falls / evasion climbs, and the gap between
the clean validation baseline and the adversarial holdout is positive.

Skips (rather than fails) when the external CSVs or the trained artifact are
absent — they are gitignored inputs, not source.

Caveat on the numbers below: the declared rule (rule.py ``is_fraud``) is a
DELIBERATELY SIMPLIFIED ground-truth PROXY — high recall vs the real labels
(~95%) but low precision (~2%, it over-flags night-hour transactions). The
co-evolution gap here measures recall loss against this DECLARED spec, NOT
catch rate against real fraud. See ``examples/targets/fraud_sparkov/README.md``.
"""

import uuid
from collections.abc import Callable, Sequence
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from orchestrator.interfaces import Adversary, Detector, Oracle
from orchestrator.loop import run_loop
from orchestrator.wiring import build_components_sparkov
from shared.persistence import create_all, make_engine, make_session_factory
from shared.persistence.models import RunRow
from shared.types import SealedSpec

from examples.targets import fraud_sparkov
from modules.measure.metrics import compute_run_metrics
from shared.llm import MockProvider

_THRESHOLD = 0.5
_N_ROUNDS = 4
_BATCH_SIZE = 400
_SEED = "sparkov-e2e"

_DATA_READY = (
    fraud_sparkov.constants.TEST_CSV.exists()
    and fraud_sparkov.MODEL_PATH.exists()
    and fraud_sparkov.constants.CHECKSUM_PATH.exists()
)
_SKIP_REASON = (
    "Sparkov real CSV / trained artifact missing (gitignored external inputs); "
    "run `python -m examples.targets.fraud_sparkov.train` after placing the data."
)


@pytest.fixture
async def sf() -> async_sessionmaker[AsyncSession]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    return make_session_factory(engine)


@pytest.mark.skipif(not _DATA_READY, reason=_SKIP_REASON)
async def test_sparkov_real_co_evolution(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    # Inject a deterministic mock judge so this loop-mechanics test makes ZERO
    # real Opus calls. The co-evolution assertions below are judge-independent;
    # the real judge's correctness is covered by the gated single-call live test
    # in modules/oracles/test_oracles.py.
    comp = build_components_sparkov(
        threshold=_THRESHOLD,
        judge_provider=MockProvider(
            text='{"vote":"pass","reason":"loop-mechanics fixture"}'
        ),
        judge_max_calls=0,
    )
    run_id = str(uuid.uuid4())
    async with sf() as s:
        s.add(
            RunRow(
                id=run_id,
                seed=_SEED,
                status="pending",
                n_rounds=_N_ROUNDS,
                batch_size=_BATCH_SIZE,
                threshold=_THRESHOLD,
                params_json={},
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
        detector=cast(Detector, comp["detector"]),
        adversary=cast(Adversary, comp["adversary"]),
        oracles=cast(Sequence[Oracle], comp["oracles"]),
        label_fn=cast(Callable[[object], bool], comp["label_fn"]),
        generate_fn=cast(Callable[[str, int], list[object]], comp["generate_fn"]),
        spec=cast(SealedSpec, comp["spec"]),
    )

    async with sf() as s:
        metrics = await compute_run_metrics(s, run_id)
    assert metrics is not None

    per_round = metrics.per_round
    assert len(per_round) == _N_ROUNDS

    detections = [r.detection_rate for r in per_round]
    evasions = [r.evasion_rate for r in per_round]
    assert all(d is not None for d in detections)
    assert all(e is not None for e in evasions)
    first_det = cast(float, detections[0])
    last_det = cast(float, detections[-1])
    first_eva = cast(float, evasions[0])
    last_eva = cast(float, evasions[-1])

    # Honest co-evolution: amt-lowering attacks erode holdout detection.
    assert last_det < first_det, (detections,)
    assert last_eva > first_eva, (evasions,)
    # The adversary actually lands evasions that preserve the true label.
    last_asr = per_round[-1].asr
    assert any(r.asr is not None and r.asr > 0 for r in per_round)
    # Gap between clean baseline and adversarial holdout is positive.
    assert metrics.gap is not None and metrics.gap > 0, metrics.gap

    # Surface the real numbers for the build report.
    print("\nSparkov real co-evolution:")
    for r in per_round:
        print(
            f"  round {r.round_index}: detection={r.detection_rate:.3f} "
            f"evasion={r.evasion_rate:.3f} asr={r.asr}"
        )
    print(f"  baseline_validation_detection={metrics.baseline_validation_detection}")
    print(f"  gap={metrics.gap:.3f}  last_asr={last_asr}")
