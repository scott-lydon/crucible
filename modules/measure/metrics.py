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
    return RunMetrics(per_round=per_round, baseline_validation_detection=baseline, gap=gap)


async def catch_rate_for_run(s: AsyncSession, run_id: str) -> float | None:
    """The platform's CATCH RATE for one red pass.

    The denominator is the red agent's SUCCESSFUL evasions — attacks that both
    ``evaded`` the detector and stayed ``true_label_preserved`` (genuinely
    positive). The numerator is how many of those the ORACLES caught: the
    aggregate verdict on the evaded sample came back FAIL (``aggregate_pass`` is
    ``False``). An evasion the detector lets through but no oracle flags is a
    platform MISS; one the oracles flag is a CATCH.

    Linkage: a successful evasion's mutated sample is re-scored in a later round
    as a MUTATED-origin transaction with the SAME ``txn_index``; if it then
    evaded the detector, the oracles voted and a verdict was recorded against
    that mutated transaction. We match attack -> mutated transaction (by
    ``txn_index``) -> verdict.

    Returns ``None`` when there were no successful evasions (catch rate is
    undefined, not zero).
    """
    attacks = await repo.attacks_for_run(s, run_id)
    successful = [a for a in attacks if a.evaded and a.true_label_preserved]
    if not successful:
        return None

    txns = await repo.transactions_for_run(s, run_id)
    verdicts = await repo.verdicts_for_run(s, run_id)
    # The mutated, evading transactions the oracles got to vote on, by txn_index.
    mutated_by_index: dict[int, list[str]] = {}
    for t in txns:
        if t.origin == Origin.MUTATED.value and not t.caught:
            mutated_by_index.setdefault(t.txn_index, []).append(t.id)
    verdict_by_txn: dict[str, VerdictRow] = {v.txn_id: v for v in verdicts}

    evaded_indices = {
        t.txn_index for t in txns if t.id in {a.txn_id for a in successful}
    }
    # Each successful-evasion lineage is one platform decision per txn_index that
    # later evaded and got an oracle verdict. Count caught (verdict FAIL).
    caught = 0
    total = 0
    for idx in evaded_indices:
        for mutated_id in mutated_by_index.get(idx, []):
            verdict = verdict_by_txn.get(mutated_id)
            if verdict is None:
                continue
            total += 1
            if not verdict.aggregate_pass:  # oracles overturned the clearance
                caught += 1
    if total == 0:
        return None
    return caught / total
