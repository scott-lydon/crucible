from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from shared.persistence import repo
from shared.persistence.models import TransactionRow, AttackRow


@dataclass(frozen=True, slots=True)
class RoundMetric:
    round_index: int
    asr: float | None
    detection_rate: float | None


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
        atks = by_round_atk.get(r.id, [])
        successes = [a for a in atks if a.evaded and a.true_label_preserved]
        asr = len(successes) / len(atks) if atks else None
        per_round.append(RoundMetric(r.round_index, asr, detection))

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
