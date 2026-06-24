from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from shared.persistence import repo
from shared.persistence.models import TransactionRow, AttackRow, VerdictRow
from shared.types.enums import Origin


@dataclass(frozen=True, slots=True)
class RoundMetric:
    round_index: int
    asr: float | None
    detection_rate: float | None
    evasion_rate: float | None


@dataclass(frozen=True, slots=True)
class RunMetrics:
    per_round: list[RoundMetric]
    baseline_validation_detection: float | None
    gap: float | None
    # US-10 cost tile: total LLM dollars for the run / number of caught hacks.
    # ``None`` (never 0.0) when there are no caught hacks or no recorded LLM calls
    # — the dashboard renders "Not yet measured".
    dollars_per_caught_hack: float | None


async def compute_run_metrics(s: AsyncSession, run_id: str) -> RunMetrics | None:
    rounds = await repo.rounds_for_run(s, run_id)
    txns = await repo.transactions_for_run(s, run_id)
    attacks = await repo.attacks_for_run(s, run_id)
    if not rounds or not txns:
        return None  # caller renders "Not yet measured"

    by_round_txn: dict[str, list[TransactionRow]] = {}
    for t in txns:
        by_round_txn.setdefault(t.round_id, []).append(t)
    by_round_atk: dict[str, list[AttackRow]] = {}
    for a in attacks:
        by_round_atk.setdefault(a.round_id, []).append(a)

    per_round: list[RoundMetric] = []
    for r in rounds:
        holdout_fraud = [t for t in by_round_txn.get(r.id, [])
                         if t.true_label and t.txn_slice == "holdout"]
        caught = [t for t in holdout_fraud if t.caught]
        detection = len(caught) / len(holdout_fraud) if holdout_fraud else None
        evasion_rate = (len(holdout_fraud) - len(caught)) / len(holdout_fraud) if holdout_fraud else None
        atks = by_round_atk.get(r.id, [])
        successes = [a for a in atks if a.evaded and a.true_label_preserved]
        asr = len(successes) / len(atks) if atks else None
        per_round.append(RoundMetric(r.round_index, asr, detection, evasion_rate))

    # baseline validation detection: round 0, validation slice
    first = rounds[0]
    val_fraud = [t for t in by_round_txn.get(first.id, [])
                 if t.true_label and t.txn_slice == "validation"]
    val_caught = [t for t in val_fraud if t.caught]
    baseline = len(val_caught) / len(val_fraud) if val_fraud else None

    # adversarial holdout detection: last round, holdout slice
    last_det = per_round[-1].detection_rate if per_round else None
    gap = (baseline - last_det) if (baseline is not None and last_det is not None) else None
    dollars = await dollars_per_caught_hack_for_run(s, run_id)
    return RunMetrics(
        per_round=per_round,
        baseline_validation_detection=baseline,
        gap=gap,
        dollars_per_caught_hack=dollars,
    )


async def catch_rate_for_run(s: AsyncSession, run_id: str) -> float | None:
    """The platform's CATCH RATE for one red pass.

    The denominator is the count of DISTINCT successful evasions that RECEIVED an
    oracle verdict — ONE decision per ``txn_index`` lineage, never more. A
    successful evasion is an attack that both ``evaded`` the detector and stayed
    ``true_label_preserved`` (genuinely positive). The numerator is how many of
    those the ORACLES caught: the aggregate verdict on the evaded sample came
    back FAIL (``aggregate_pass`` is ``False``). An evasion the detector lets
    through but no oracle flags is a platform MISS; one the oracles flag is a
    CATCH.

    Linkage (and the round model): a successful evasion's mutated sample is
    re-scored in the NEXT round as a MUTATED-origin transaction with the SAME
    ``txn_index``; if it then evades the detector, the oracles vote and a verdict
    is recorded against that mutated transaction. An evasion therefore enters the
    denominator ONCE it has a verdict. We match attack lineage -> mutated
    transaction (by ``txn_index``) -> verdict, deduping to ONE verdict per
    ``txn_index`` (the latest-round mutated, evading row for that lineage). This
    is why a lineage that is mutated again across several rounds is NOT
    double-counted.

    Consequences this definition is honest about:

    * A successful evasion landed in the FINAL round is never re-scored (there is
      no next round), so it has no verdict and does not enter the denominator. In
      particular an ``n_rounds == 1`` pass produces NO countable decisions —
      every attack is round-0 and is never re-scored. The catch rate is then
      genuinely UNDEFINED, not zero: this function returns ``None``. The rate is
      only meaningful for ``n_rounds >= 2``.

    Returns ``None`` when no successful evasion received a verdict (catch rate is
    undefined, not zero) — including the zero-successful-evasion case.
    """
    counts = await _caught_hack_counts(s, run_id)
    if counts is None:  # no successful evasion got a verdict (e.g. n_rounds == 1)
        return None
    caught, total = counts
    return caught / total


async def _caught_hack_counts(
    s: AsyncSession, run_id: str
) -> tuple[int, int] | None:
    """``(caught, total)`` decisions for the run, or ``None`` when undefined.

    The single source of truth for the catch-rate "caught" definition (a
    successful evasion the ORACLES voted FAIL on), reused by both
    ``catch_rate_for_run`` and the dollars-per-caught-hack tile. Returns ``None``
    when no successful evasion received a verdict (rate is undefined, not zero) —
    including the zero-successful-evasion case.
    """
    attacks = await repo.attacks_for_run(s, run_id)
    successful = [a for a in attacks if a.evaded and a.true_label_preserved]
    if not successful:
        return None

    txns = await repo.transactions_for_run(s, run_id)
    rounds = await repo.rounds_for_run(s, run_id)
    verdicts = await repo.verdicts_for_run(s, run_id)
    round_index_by_id = {r.id: r.round_index for r in rounds}
    verdict_by_txn: dict[str, VerdictRow] = {v.txn_id: v for v in verdicts}

    # The txn_index lineages the red agent successfully evaded (its attack's
    # caught parent shares the txn_index of the mutated, re-scored child).
    successful_txn_ids = {a.txn_id for a in successful}
    evaded_indices = {t.txn_index for t in txns if t.id in successful_txn_ids}

    # For each evaded lineage, pick the SINGLE canonical decision: the latest-round
    # mutated, evading transaction that the oracles actually voted on. Deduping to
    # one per txn_index is what stops a lineage mutated across rounds from being
    # counted more than once.
    canonical: dict[int, VerdictRow] = {}
    canonical_round: dict[int, int] = {}
    for t in txns:
        if t.origin != Origin.MUTATED.value or t.caught:
            continue
        if t.txn_index not in evaded_indices:
            continue
        verdict = verdict_by_txn.get(t.id)
        if verdict is None:
            continue
        r_idx = round_index_by_id.get(t.round_id, -1)
        if t.txn_index not in canonical or r_idx > canonical_round[t.txn_index]:
            canonical[t.txn_index] = verdict
            canonical_round[t.txn_index] = r_idx

    if not canonical:  # no successful evasion got a verdict (e.g. n_rounds == 1)
        return None
    caught = sum(1 for v in canonical.values() if not v.aggregate_pass)
    return caught, len(canonical)


async def dollars_per_caught_hack_for_run(
    s: AsyncSession, run_id: str
) -> float | None:
    """US-10 cost tile: total recorded LLM dollars for the run / caught hacks.

    A caught hack reuses the catch-rate "caught" definition: a successful evasion
    the ORACLES voted FAIL on. The numerator is the sum of ``dollars`` over the
    run's persisted ``llm_calls`` (recorded by ``PersistingLLMProvider``).

    Honest ``None`` (never 0.0 — the dashboard renders "Not yet measured") when
    there are zero caught hacks OR zero recorded LLM calls, so the tile is never a
    misleading sample.
    """
    counts = await _caught_hack_counts(s, run_id)
    if counts is None:
        return None
    caught, _ = counts
    if caught == 0:
        return None
    calls = await repo.llm_calls_for_run(s, run_id)
    if not calls:
        return None
    total_dollars = sum(c.dollars for c in calls)
    return total_dollars / caught
