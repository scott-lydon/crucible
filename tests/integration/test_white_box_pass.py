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
from shared.persistence.models import (
    AttackRow,
    RoundRow,
    RunRow,
    TransactionRow,
    VerdictRow,
)
from shared.types.enums import Origin
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


async def _seed_evasion_lineage(
    sf: async_sessionmaker[AsyncSession],
    run_id: str,
    *,
    txn_index: int,
    verdict_passes: list[bool],
) -> None:
    """Seed ONE successful-evasion lineage that re-evades across several rounds.

    For ``txn_index`` we write: a round-0 caught SYNTHETIC parent + a successful
    AttackRow against it, then one MUTATED, uncaught transaction PER later round
    (rounds 1..N), each with its own oracle verdict (``aggregate_pass`` taken from
    ``verdict_passes``). This is exactly the shape that made the old code
    double-count: many mutated/uncaught rows for a single evaded index. The run
    row is created by the caller (so multiple lineages share one run).
    """
    parent_id = str(uuid.uuid4())
    async with sf() as s:
        round0 = str(uuid.uuid4())
        s.add(RoundRow(id=round0, run_id=run_id, round_index=0))
        await s.flush()
        s.add(TransactionRow(
            id=parent_id, run_id=run_id, round_id=round0, txn_index=txn_index,
            features_json={}, true_label=True, origin=Origin.SYNTHETIC.value,
            txn_slice="holdout", parent_txn_id=None, detector_score=0.9,
            caught=True, seed="dc",
        ))
        s.add(AttackRow(
            id=str(uuid.uuid4()), run_id=run_id, round_id=round0, txn_id=parent_id,
            parent_txn_id=parent_id, mutation_json={}, pre_score=0.9, post_score=0.1,
            evaded=True, true_label_preserved=True, seed="dc",
        ))
        await s.commit()

    for r_idx, passes in enumerate(verdict_passes, start=1):
        async with sf() as s:
            round_id = str(uuid.uuid4())
            s.add(RoundRow(id=round_id, run_id=run_id, round_index=r_idx))
            await s.flush()
            txn_id = str(uuid.uuid4())
            s.add(TransactionRow(
                id=txn_id, run_id=run_id, round_id=round_id, txn_index=txn_index,
                features_json={}, true_label=True, origin=Origin.MUTATED.value,
                txn_slice="holdout", parent_txn_id=parent_id, detector_score=0.1,
                caught=False, seed="dc",
            ))
            await s.flush()
            s.add(VerdictRow(
                id=str(uuid.uuid4()), run_id=run_id, round_id=round_id, txn_id=txn_id,
                aggregate_pass=passes, fail_weight=0.0 if passes else 1.0,
                pass_weight=1.0 if passes else 0.0, audit_trace_json={}, seed="dc",
            ))
            await s.commit()


async def test_catch_rate_dedupes_per_txn_index_no_double_count(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    """A single evaded lineage counts ONCE, even with many mutated verdicts.

    Two evaded indices. Index 0 has THREE mutated/uncaught verdicts whose LATEST
    (round 3) is a CATCH (FAIL); index 1 has ONE verdict that is a MISS (PASS).
    Denominator is the 2 distinct lineages (not the 4 mutated rows); numerator is
    the 1 caught lineage -> exactly 0.5. A raw-row tally over the 4 rows would be
    1/4 = 0.25, so this asserts dedup, not a coincidental count.
    """
    run_id = str(uuid.uuid4())
    await _seed_run(sf, run_id)
    # index 0: 3 verdicts, latest (round 3) is a CATCH; index 1: 1 verdict, a MISS.
    await _seed_evasion_lineage(sf, run_id, txn_index=0,
                                verdict_passes=[True, True, False])
    await _seed_evasion_lineage(sf, run_id, txn_index=1,
                                verdict_passes=[True])

    async with sf() as s:
        rate = await catch_rate_for_run(s, run_id)
    # 2 distinct lineages, 1 caught -> 0.5. Raw-row tally would be 1/4 = 0.25.
    assert rate == 0.5


async def test_catch_rate_latest_round_canonical_not_raw_row_count(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    """Dedup picks the LATEST-round verdict per index, not a raw-row tally.

    One evaded index with THREE mutated verdicts: PASS, PASS, FAIL (latest is the
    CATCH). Distinct-lineage rate = 1/1 = 1.0. A raw-row tally would be 1/3.
    """
    run_id = str(uuid.uuid4())
    await _seed_run(sf, run_id)
    await _seed_evasion_lineage(sf, run_id, txn_index=0,
                                verdict_passes=[True, True, False])
    async with sf() as s:
        rate = await catch_rate_for_run(s, run_id)
    assert rate == 1.0  # one distinct caught lineage; NOT 1/3 raw rows


async def test_catch_rate_n_rounds_one_is_undefined_none(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    """An ``n_rounds == 1`` pass yields NO verdict per evasion -> honest ``None``.

    Round-0 attacks evade but their mutated samples are never re-scored (no next
    round), so no successful evasion gets a verdict. Despite real successful
    evasions, the catch rate is genuinely undefined — ``None``, not a fake 0/1.
    """
    run_id = str(uuid.uuid4())
    await _seed_run(sf, run_id)
    await run_loop(
        sf, run_id=run_id, seed="wb", n_rounds=1, batch_size=6,
        threshold=_THRESHOLD, detector=_Detector(),
        adversary=_FixedAmtAdversary(amt=2.0),
        oracles=_ORACLES, label_fn=_is_fraud, generate_fn=_generate, spec=_SPEC,
    )
    async with sf() as s:
        attacks = await repo.attacks_for_run(s, run_id)
        rate = await catch_rate_for_run(s, run_id)
    # Real successful evasions exist, but none received a verdict (never re-scored).
    assert any(a.evaded and a.true_label_preserved for a in attacks)
    assert rate is None
