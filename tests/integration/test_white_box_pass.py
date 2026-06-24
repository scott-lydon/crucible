"""White-box red pass (US-14 / slice-12), fully offline & deterministic.

Constructs a controlled scenario with two heuristic oracles (each weight 0.5, so
the aggregate FAILs only when BOTH fire — fail_weight >= 1.0) and two mock
adversaries that make ZERO LLM calls:

* the BLACK-BOX adversary drives the evaded feature very low, tripping BOTH
  heuristics -> the evasion is CAUGHT;
* the WHITE-BOX (informed) adversary, knowing the verifiers, lands the feature in
  the narrow band that still evades the detector but trips only ONE heuristic ->
  the evasion is MISSED.

So the platform's white-box catch rate (0.0) is strictly below the black-box
catch rate (1.0) and the reported gap is 1.0 — the sanity property
``white_box <= black_box`` holds and the gap is demonstrated. We assert the
catch rates + gap are computed, persisted, and exposed at ``/metrics``. No
Postgres (in-memory SQLite); no real Sonnet/Opus calls.
"""

import uuid
from dataclasses import dataclass, replace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modules.measure.metrics import catch_rate_for_run
from modules.oracles.scheme import verification_scheme
from orchestrator.full_run import run_white_box_pass
from orchestrator.interfaces import Oracle
from orchestrator.loop import run_loop
from shared.persistence import create_all, make_engine, make_session_factory, repo
from shared.persistence.models import RunRow
from shared.types import OracleKind, OracleVote, VerdictContext, Vote, sealed_spec_from_yaml

_SPEC = sealed_spec_from_yaml(
    """
target_kind: fraud
obligations:
  - flag truly fraudulent transactions
invariants: []
metamorphic_relations:
  - name: amt_decrease_label_invariance
    description: Lowering amount does not change the true fraud label.
    feature: amt
    direction: decrease
    label_must_change: false
holdout_generator_kind: deterministic_real_sample
"""
)

_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class _Txn:
    txn_index: int
    amt: float
    hour: int


def _detector_score(sample: object) -> float:
    # Amount-reliant detector: clears once amt drops to/below 100.
    return 0.9 if getattr(sample, "amt") > 100.0 else 0.1


class _Detector:
    """Amount-reliant detector satisfying the Detector protocol."""

    def score(self, sample: object) -> float:
        return _detector_score(sample)


def _is_fraud(sample: object) -> bool:
    # Night-hour fraud regardless of amount: lowering amt preserves the label.
    return getattr(sample, "hour") in {0, 1, 2, 3}


def _generate(seed: str, n: int) -> list[object]:
    # All caught night-frauds in the holdout slice (odd indices are holdout).
    return [_Txn(txn_index=i, amt=1500.0, hour=2) for i in range(n)]


class _LowAmtHeuristic:
    """Weight-0.5 heuristic: FAILs an evasion that drove amt below 50."""

    @property
    def kind(self) -> OracleKind:
        return OracleKind.INVARIANT

    def describe(self) -> str:
        return "low-amt heuristic: fails when a cleared fraud has amt < 50."

    def vote(self, ctx: VerdictContext) -> OracleVote:
        cleared = ctx.detector_score < ctx.threshold
        fails = cleared and _is_fraud(ctx.sample) and getattr(ctx.sample, "amt") < 50.0
        return OracleVote(
            kind=self.kind,
            vote=Vote.FAIL if fails else Vote.PASS,
            weight=0.5,
            reason="amt<50 on a cleared fraud" if fails else "amt not suspiciously low",
            evidence={"amt": getattr(ctx.sample, "amt")},
        )


class _ClearedFraudHeuristic:
    """Weight-0.5 heuristic: FAILs any cleared still-fraud sample."""

    @property
    def kind(self) -> OracleKind:
        return OracleKind.METAMORPHIC

    def describe(self) -> str:
        return "cleared-fraud heuristic: fails when the detector clears a still-fraud."

    def vote(self, ctx: VerdictContext) -> OracleVote:
        cleared = ctx.detector_score < ctx.threshold
        fails = cleared and _is_fraud(ctx.sample)
        return OracleVote(
            kind=self.kind,
            vote=Vote.FAIL if fails else Vote.PASS,
            weight=0.5,
            reason="cleared a still-fraud" if fails else "ok",
            evidence={},
        )


_ORACLES: list[Oracle] = [_LowAmtHeuristic(), _ClearedFraudHeuristic()]


class _FixedAmtAdversary:
    """Deterministic, zero-LLM adversary that sets amt to a fixed value."""

    def __init__(self, amt: float) -> None:
        self._amt = amt

    def mutate(self, sample: object, score: float) -> object | None:
        candidate = replace(sample, amt=self._amt)  # type: ignore[type-var]
        if _detector_score(candidate) < _THRESHOLD and _is_fraud(candidate):
            return candidate
        return None


@pytest.fixture
async def sf() -> async_sessionmaker[AsyncSession]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    return make_session_factory(engine)


async def _seed_run(sf: async_sessionmaker[AsyncSession], run_id: str) -> None:
    async with sf() as s:
        s.add(
            RunRow(
                id=run_id, seed="wb", status="running", n_rounds=2,
                batch_size=6, threshold=_THRESHOLD, params_json={},
            )
        )
        await s.commit()


def test_verification_scheme_is_generic_and_lists_verifiers() -> None:
    scheme = verification_scheme(_ORACLES)
    assert "low-amt heuristic" in scheme
    assert "cleared-fraud heuristic" in scheme
    # numbered, one line per oracle
    assert scheme.startswith("1.")
    assert "2." in scheme


async def test_white_box_catch_rate_at_most_black_box_with_gap(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    black_id = str(uuid.uuid4())
    await _seed_run(sf, black_id)

    # BLACK-BOX pass: drives amt to 2 (< 50) -> trips BOTH heuristics -> CAUGHT.
    await run_loop(
        sf, run_id=black_id, seed="wb", n_rounds=2, batch_size=6,
        threshold=_THRESHOLD, detector=_Detector(),
        adversary=_FixedAmtAdversary(amt=2.0),
        oracles=_ORACLES, label_fn=_is_fraud, generate_fn=_generate, spec=_SPEC,
    )

    # WHITE-BOX pass: informed adversary lands amt at 60 (evades detector, but
    # >= 50 so the low-amt heuristic stays silent) -> only ONE heuristic fires
    # -> aggregate fail_weight 0.5 < 1.0 -> MISSED.
    await run_white_box_pass(
        sf, black_box_run_id=black_id, seed="wb", n_rounds=2, batch_size=6,
        threshold=_THRESHOLD, detector=_Detector(),
        white_box_adversary=_FixedAmtAdversary(amt=60.0),
        oracles=_ORACLES, label_fn=_is_fraud, generate_fn=_generate, spec=_SPEC,
    )

    async with sf() as s:
        black = await catch_rate_for_run(s, black_id)
        row = await repo.white_box_metrics_for_run(s, black_id)

    assert black == 1.0  # both heuristics fired -> every evasion caught
    assert row is not None
    assert row.black_box_catch_rate == 1.0
    assert row.white_box_catch_rate == 0.0  # informed attacker slipped a heuristic
    assert row.white_box_gap == pytest.approx(1.0)
    # SANITY: an informed attacker is caught no more often than an ignorant one.
    assert row.white_box_catch_rate <= row.black_box_catch_rate
    assert row.white_box_run_id is not None and row.white_box_run_id != black_id
