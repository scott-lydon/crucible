"""Export the seeded-hack corpus: successful evasions with full audit traces.

A corpus entry is one SUCCESSFUL attack — one that both ``evaded`` the detector
AND stayed ``true_label_preserved`` (genuinely positive). Each entry carries the
attack id, the target type, the tactic (which feature the red agent moved and in
which direction), the mutated prompt/features, the oracle audit trace for the
re-scored sample, the dollars at stake, and the capture timestamp.

Everything is read from REAL persisted rows (attacks, transactions, verdicts).
No LLM, no fabricated values: an empty corpus yields an empty list / empty file,
never a placeholder row. The JSONL line count is therefore EXACTLY the table row
count — the central US-11 invariant.
"""

import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from shared.persistence import repo
from shared.persistence.models import AttackRow, TransactionRow, VerdictRow


@dataclass(frozen=True, slots=True)
class CorpusEntry:
    """One successful-evasion corpus row, ready to serialize as a JSONL line."""

    attack_id: str
    target_type: str
    tactic: str
    prompt: dict[str, object]
    audit_trace: dict[str, object]
    dollars: float
    captured_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "attack_id": self.attack_id,
            "target_type": self.target_type,
            "tactic": self.tactic,
            "prompt": self.prompt,
            "audit_trace": self.audit_trace,
            "dollars": self.dollars,
            "captured_at": self.captured_at,
        }


def _tactic_from_mutation(mutation_json: dict[str, object]) -> str:
    """Derive a human tactic label from the mutation's before/after features.

    The red loop records ``{"from_features": {...}, "to_features": {...}}``. The
    tactic is the set of features that changed and the direction of the change,
    e.g. ``amt:down`` — exactly what a downstream auditor needs to cluster the
    corpus. Falls back to ``"unknown"`` only when the mutation carries no diff
    (never fabricated).
    """
    frm = mutation_json.get("from_features")
    to = mutation_json.get("to_features")
    if not isinstance(frm, dict) or not isinstance(to, dict):
        return "unknown"
    moves: list[str] = []
    for key in sorted(frm):
        before, after = frm.get(key), to.get(key)
        if before == after:
            continue
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            direction = "up" if after > before else "down"
            moves.append(f"{key}:{direction}")
        else:
            moves.append(f"{key}:changed")
    return ",".join(moves) if moves else "unknown"


def _dollars_from_features(features: object) -> float:
    """The dollars at stake for a sample: its ``amt`` feature, else 0.0.

    Honest: a target with no monetary feature genuinely has 0 dollars at stake
    for this entry — that is a real value, not a fabricated stand-in.
    """
    if isinstance(features, dict):
        amt = features.get("amt")
        if isinstance(amt, (int, float)):
            return float(amt)
    return 0.0


def _entry(
    attack: AttackRow,
    txn: TransactionRow | None,
    verdict: VerdictRow | None,
) -> CorpusEntry:
    mutation = cast(dict[str, object], attack.mutation_json or {})
    prompt = cast(dict[str, object], mutation.get("to_features") or {})
    audit: dict[str, object] = verdict.audit_trace_json if verdict else {}
    # Dollars from the mutated (post-evasion) features if available, else the
    # re-scored transaction's features.
    dollars = _dollars_from_features(prompt)
    if dollars == 0.0 and txn is not None:
        dollars = _dollars_from_features(txn.features_json)
    return CorpusEntry(
        attack_id=attack.id,
        target_type=attack.pillar,
        tactic=_tactic_from_mutation(mutation),
        prompt=prompt,
        audit_trace=audit,
        dollars=dollars,
        captured_at=attack.created_at.isoformat(),
    )


async def corpus_entries(
    s: AsyncSession, run_id: str | None = None
) -> list[CorpusEntry]:
    """The corpus rows: every successful evasion for ``run_id`` (or all runs).

    Successful = ``evaded`` AND ``true_label_preserved``. Returns ``[]`` when no
    attack succeeded (honest empty corpus). The audit trace is the verdict on the
    re-scored mutated transaction sharing the attack's ``txn_index`` lineage, if
    one was recorded; otherwise an empty trace (the evasion landed in the final
    round and was never re-scored — never invented).
    """
    if run_id is not None:
        attacks: Sequence[AttackRow] = await repo.attacks_for_run(s, run_id)
        txns: Sequence[TransactionRow] = await repo.transactions_for_run(s, run_id)
        verdicts: Sequence[VerdictRow] = await repo.verdicts_for_run(s, run_id)
    else:
        attacks = await repo.all_attacks(s)
        txns = await repo.all_transactions(s)
        verdicts = await repo.all_verdicts(s)

    successful = [a for a in attacks if a.evaded and a.true_label_preserved]
    # Map the attack's evaded lineage -> the re-scored mutated transaction's
    # verdict (matched by txn_index within the same run).
    txn_by_id = {t.id: t for t in txns}
    index_by_run: dict[tuple[str, int], list[TransactionRow]] = {}
    for t in txns:
        index_by_run.setdefault((t.run_id, t.txn_index), []).append(t)
    verdict_by_txn = {v.txn_id: v for v in verdicts}

    entries: list[CorpusEntry] = []
    for a in successful:
        parent = txn_by_id.get(a.txn_id)
        verdict: VerdictRow | None = None
        if parent is not None:
            # the mutated re-score of this lineage carries the oracle verdict
            for t in index_by_run.get((a.run_id, parent.txn_index), []):
                v = verdict_by_txn.get(t.id)
                if v is not None:
                    verdict = v
                    break
        entries.append(_entry(a, parent, verdict))
    return entries


async def corpus_jsonl(s: AsyncSession, run_id: str | None = None) -> AsyncIterator[str]:
    """Stream the corpus as JSONL — one compact JSON object per line.

    The number of lines yielded is EXACTLY ``len(corpus_entries(...))``: one line
    per successful evasion, zero lines for an empty corpus. (US-11 invariant.)
    """
    for entry in await corpus_entries(s, run_id):
        yield json.dumps(entry.to_dict(), separators=(",", ":")) + "\n"
