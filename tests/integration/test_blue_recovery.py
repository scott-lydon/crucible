"""The DEMO test — the red -> blue -> recover arc on REAL Sparkov data.

ZERO real LLM calls: the red loop runs on its FREE deterministic fallback (Sonnet
budget 0, mock judge budget 0) and the blue proposer uses a MockProvider proposing
{"features_to_add": ["hour", "distance"]} (the budget-0 deterministic fallback
would propose the same unused features). Nothing in this path is mocked except the
LLM seams — the detector, the data, the mutator, and the retraining are all REAL.

Arc:
1. Run the real red loop -> the amt-lowering adversary lands evasions on the
   amt-reliant LightGBM detector. Harvest the mutated, still-fraud,
   old-detector-cleared transactions as the holdout.
2. run_blue_round -> retrains a NEW LightGBM WITH hour (+distance), validates on
   the holdout.
3. ASSERT detection_after > detection_before AND detection_after materially > 0:
   the retrained model genuinely catches the amt-lowered night-fraud evasions the
   old model missed. Honest recovery, not a rigged number.

Skips (not fails) when the external CSVs / artifact are absent.
"""

import uuid
from collections.abc import Callable, Sequence
from typing import cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from orchestrator.interfaces import Adversary, Detector, Oracle
from orchestrator.loop import run_loop
from orchestrator.wiring import build_components_sparkov
from shared.persistence import create_all, make_engine, make_session_factory
from shared.persistence.models import AttackRow, RunRow
from shared.types import SealedSpec

from examples.targets import fraud_sparkov
from examples.targets.fraud_sparkov.record import SparkovTxn
from modules.blue import run_blue_round
from modules.blue.proposer import BlueProposer
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


@pytest.fixture
async def sf() -> async_sessionmaker[AsyncSession]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    return make_session_factory(engine)


def _txn_from_features(features: dict[str, object]) -> SparkovTxn:
    """Reconstruct the opaque victim record from a persisted feature map."""
    return SparkovTxn(
        txn_index=int(cast(int, features["txn_index"])),
        amt=float(cast(float, features["amt"])),
        cat_risk=int(cast(int, features["cat_risk"])),
        hour=int(cast(int, features["hour"])),
        age=int(cast(int, features["age"])),
        city_pop=int(cast(int, features["city_pop"])),
        distance=float(cast(float, features.get("distance", 0.0))),
    )


@pytest.mark.skipif(not _DATA_READY, reason=_SKIP_REASON)
async def test_blue_recovers_on_real_evasions(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    # Build with every LLM seam neutralized: zero real Sonnet/Opus calls.
    comp = build_components_sparkov(
        threshold=_THRESHOLD,
        judge_provider=MockProvider(text='{"vote":"pass","reason":"fixture"}'),
        judge_max_calls=0,
        red_provider=MockProvider(text='{"feature":"amt","new_value":1.0,"rationale":"x"}'),
        red_max_calls=0,
    )
    detector = cast(Detector, comp["detector"])
    label_fn = cast(Callable[[object], bool], comp["label_fn"])

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

    # Harvest the mutated, still-fraud, old-detector-cleared transactions.
    async with sf() as s:
        rows = (
            await s.execute(
                select(AttackRow).where(
                    AttackRow.run_id == run_id,
                    AttackRow.evaded.is_(True),
                    AttackRow.true_label_preserved.is_(True),
                )
            )
        ).scalars().all()

    holdout: list[object] = []
    seen: set[int] = set()
    for row in rows:
        to_features = cast(dict[str, object], row.mutation_json["to_features"])
        sample = _txn_from_features(to_features)
        if sample.txn_index in seen:
            continue
        seen.add(sample.txn_index)
        holdout.append(sample)

    assert holdout, "red loop produced no successful evasions to recover from"

    # Sanity: the OLD detector indeed clears these (that is why they evaded).
    old_cleared = sum(1 for s in holdout if detector.score(s) < _THRESHOLD)
    assert old_cleared == len(holdout), (
        "holdout must be samples the old detector cleared",
        old_cleared,
        len(holdout),
    )

    # --- 2. run the real blue round (mock proposer, REAL retrain) ----------
    blue_proposer = BlueProposer(
        provider=MockProvider(
            text='{"features_to_add":["hour","distance"],"rationale":"close blind spot"}'
        ),
        max_calls=5,
    )
    result = run_blue_round(
        catalog=comp["catalog"],
        current_features=cast(Sequence[str], comp["current_features"]),
        available_features=cast(Sequence[str], comp["available_features"]),
        retrain_fn=cast(Callable[[Sequence[str]], object], comp["retrain_fn"]),
        holdout_samples=holdout,
        label_fn=label_fn,
        threshold=_THRESHOLD,
        proposer=blue_proposer,
        old_detector=detector,
    )

    v = result.validation
    # --- 3. assert honest recovery ----------------------------------------
    assert v.n == len(holdout)
    assert v.detection_before == pytest.approx(0.0, abs=1e-9), v.detection_before
    assert v.detection_after > v.detection_before, (v.detection_before, v.detection_after)
    # Materially > 0: the retrained model catches a real share of the evasions.
    assert v.detection_after > 0.3, v.detection_after
    assert "hour" in result.new_features

    print("\nBlue recovery on REAL Sparkov evasions:")
    print(f"  holdout evasions (n)   = {v.n}")
    print(f"  proposed features      = {result.patch.features_to_add}")
    print(f"  new detector features  = {result.new_features}")
    print(f"  detection_before       = {v.detection_before:.3f}")
    print(f"  detection_after        = {v.detection_after:.3f}")
    print(f"  recovered              = {v.recovered:.3f}")
    print(f"  new model path         = {result.new_model_path}")
