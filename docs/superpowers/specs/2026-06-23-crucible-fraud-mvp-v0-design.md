# Crucible Fraud MVP v0 — Design

**Date:** 2026-06-23
**Status:** Approved (brainstorming complete; ready for implementation plan)
**Branch:** `fraud-mvp-v0` (never committed to `main`)

This is the design for the first runnable vertical slice of Crucible: a **local, honest demo of the red/blue fraud-evaluation loop**. It is a deliberate, scoped-down realization of `spec.md` / `plan.md` / `constitution.md`, not a replacement for them. Where this document relaxes a constitutional rule, it says so explicitly under [§9 Constitutional deviations](#9-constitutional-deviations-conscious-v0-only).

---

## 1. Goal (one paragraph)

Prove the *shape* of the Crucible thesis end to end on a single machine, with no external services: an operator launches a fraud-evaluation run; the system generates synthetic transactions with deterministic ground-truth fraud labels; a deliberately-flawed detector scores them; a mock adversary mutates caught frauds to evade the detector while keeping them genuinely fraudulent; five oracles vote on whether the detector's decisions are sound; and a dashboard shows attack success rate climbing, detection rate falling, and the validation-vs-held-out gap widening — every number computed from persisted rows only, never faked. The point the demo lands: **the detector learned a cheap proxy (`amount`) rather than the real causal signals, and an adversary who knows that walks straight through the gap.**

## 2. Scope

### In scope (the seven required elements)

1. Operator launches a fraud-evaluation run.
2. System creates synthetic transactions with deterministic fraud labels.
3. A deliberately-flawed fraud detector scores them.
4. A red/mock adversary mutates transactions to evade detection.
5. Five oracles evaluate the output: held-out ground-truth, metamorphic, invariant/rule, differential **stub**, LLM-judge **mock** (marked one vote).
6. Dashboard shows: attack success rate, detection rate, validation-vs-held-out gap, verdict drilldown, oracle vote cards.
7. Metrics come from persisted rows only. With no real data, the UI renders the literal text **"Not yet measured."**

### Out of scope (v0)

No real bank data. No real payment-processor data. No real Modal sandbox. No real SR 11-7 PDF export. No real blue retraining. No real external LLM calls unless everything else works. No multi-agent product architecture inside Crucible yet. **No fake metrics.**

## 3. Architecture & layout

Foundation-first: the v0 layout is a strict subset of the hexagonal layout in `plan.md §2`, using the *same paths*, so later slices grow into it rather than replacing it.

```
crucible/
  pyproject.toml            # py3.12, fastapi, sqlalchemy[asyncio], aiosqlite, pydantic,
                            #   pytest-asyncio, ruff, mypy --strict
  shared/
    types/                  # frozen+slots dataclasses: Transaction, Attack, Verdict,
                            #   OracleVote, ids, enums
    persistence/            # async engine (sqlite+aiosqlite), ORM models, typed repo fns
  orchestrator/
    interfaces/             # Protocols (NOT abstract base classes — constitution §2):
                            #   Detector, Adversary, Oracle
    loop.py                 # runs N rounds, writes audit rows, ZERO business logic
    api.py                  # FastAPI: POST /runs, GET /runs/:id, GET /runs/:id/metrics, GET /health
    wiring.py               # DI — only file importing both concretes and interfaces
  modules/
    targets/synth/          # deterministic synthetic transaction generator
    targets/fraud_detector/ # the deliberately-flawed detector
    red/mutator/            # the mock adversary
    oracles/{held_out,metamorphic,invariant,differential_stub,llm_judge_mock,aggregator}/
    measure/metrics.py      # computes ASR / detection / gap FROM ROWS ONLY
  dashboard/                # React + Vite + Tailwind + Recharts
  tests/integration/
```

**Module rules (constitution §2)** apply from day one: modules import only from `shared/` and `orchestrator/interfaces/`; no module imports another module; interfaces are `typing.Protocol`; `wiring.py` is the only file allowed to import both a concrete class and its interface; `loop.py` holds no business logic.

## 4. The four moving parts

### 4.1 Synthetic transactions (`modules/targets/synth/`)

Seeded RNG; the seed is captured on the `runs` row so any run replays byte-equal. Each transaction carries features `{amount, velocity, country_mismatch, merchant_risk, hour_of_day}`. The **ground-truth fraud rule** (independent of the detector, never exposed to detector or adversary):

```
is_fraud = (velocity > V_THRESH)
           OR country_mismatch
           OR (amount > A_HIGH AND merchant_risk > 0.7)
```

A batch is ~200 transactions, ~20% fraud. Synthetic ≠ fake: labels are honestly derived from a fixed causal rule and fully reproducible.

### 4.2 Deliberately-flawed detector (`modules/targets/fraud_detector/`)

A mostly-`amount`-weighted logistic scorer — *not* amount-only, so the flaw reads as credible over-reliance rather than a cartoon:

```
score = sigmoid( 2.8 * normalized_amount
               + 0.15 * merchant_risk
               + 0.05 * velocity
               + 0.03 * country_mismatch
               - bias )
caught = score >= threshold
```

The claim this supports: *"the detector over-relies on the easiest visible proxy (`amount`) and underweights the true causal signals (`velocity`, `country_mismatch`)."* It catches big-dollar fraud and is silently blind to low-amount-but-otherwise-fraudulent transactions.

### 4.3 Mock adversary (`modules/red/mutator/`) — explicitly not a real LLM

Deterministic mutator. Given a fraud transaction the detector **caught**, it applies a minimal mutation that lowers the detector's score (pushes `amount` toward the blind spot) while **preserving `velocity`/`country_mismatch` so the transaction stays genuinely fraudulent**. Hard constraint: a mutation that would flip the true label is **rejected** — the adversary only ever produces transactions that are *still real fraud but now evade the flawed detector*. Each attempt writes one `attacks` row recording `pre_score`, `post_score`, `evaded`, `true_label_preserved`.

### 4.4 The loop (`orchestrator/loop.py`)

One run = N rounds (default 5, configurable). The batch is split deterministically into a **validation slice** (never adversarially attacked — the baseline reference) and a **held-out slice** (the adversary's target). Per round:

1. Detector scores the current batch; `caught = score >= threshold`.
2. For each caught fraud in the held-out slice, the adversary proposes a mutation (feedback = detector score); the mutated transaction replaces it for the next round.
3. Detector re-scores; oracles vote on each cleared transaction.
4. Persist round / attack / verdict / oracle-vote rows, each carrying `seed`, `round_id`, `pillar`, `created_at`.

Across rounds, ASR climbs and detection falls **organically from the mechanics** — nothing is scripted or faked. `loop.py` only calls interfaces in sequence and writes rows; any conditional belongs in a module.

## 5. Data model (SQLite, async SQLAlchemy)

Every work-row carries `seed`, `pillar`, `created_at` (constitution §7, v0 subset).

| Table | Key columns |
|---|---|
| `runs` | `id, seed, status, n_rounds, batch_size, threshold, params_json, created_at` |
| `rounds` | `id, run_id, round_index, created_at` |
| `transactions` | `id, run_id, round_id, txn_index, features_json, true_label, origin∈{synthetic,mutated}, slice∈{validation,holdout}, parent_txn_id, detector_score, caught` |
| `attacks` | `id, run_id, round_id, txn_id, parent_txn_id, mutation_json, pre_score, post_score, evaded, true_label_preserved, seed, pillar` |
| `verdicts` | `id, run_id, round_id, txn_id, aggregate_pass, vote_tally, audit_trace_json, seed` |
| `oracle_votes` | `id, verdict_id, oracle_kind, vote∈{pass,fail,abstain}, weight, reason, evidence_json` |

**Metrics are never stored.** They are computed from these rows on read by `modules/measure/metrics.py`. Zero contributing rows → the API returns a typed empty state that the UI renders as **"Not yet measured."** — never `0.0`.

## 6. The three headline metrics (precise definitions)

1. **Attack success rate (ASR)** — *per attempted mutation*.
   `ASR = successful_evasions / attempted_mutations`, where a success means `true_label_preserved AND post_score < threshold`. One `attacks` row per attempt. Rises as the adversary learns the blind spot.

2. **Detection rate** — *per population, per round*.
   `detection_rate = caught_true_frauds / all_true_fraud_txns_in_population`. The round-over-round chart that *falls* is computed over the **held-out slice** (the attacked population) for each round. The **validation slice** is measured once, unattacked, as the fixed baseline that feeds the gap. Different denominator from ASR (ASR is per *mutation attempt*; detection is per *true-fraud transaction*); the two are not conflated.

3. **Validation-vs-held-out gap.**
   `gap = baseline_validation_detection_rate − adversarial_holdout_detection_rate`.
   Both terms are the **detector's** detection rate, measured on two populations: the clean validation slice (never attacked) versus the adversarially-mutated held-out slice. The **held-out oracle has no catch rate of its own** — it *certifies ground truth* and grades whether the detector missed a true-fraud case, which is what makes the held-out detection number trustworthy. The gap widens as the adversary succeeds; it is the silent-wrongness measure and maps onto the SR 11-7 "validation overstated robustness" story.

## 7. The five oracles & verdict semantics

A **verdict** answers, for each transaction the detector *cleared*: is that "clean" decision **sound**? `fail` = the oracles caught a true fraud the detector was fooled into clearing — i.e., the platform caught what the flawed detector missed.

| Oracle | v0 behavior | Weight | UI label |
|---|---|---|---|
| `held_out` (ground-truth) | Independent label authority: computes the true fraud label from the sealed causal rule (never optimized against by detector/adversary) and grades whether the detector missed a true fraud. | 1.0 | — |
| `metamorphic` | Checks relations from spec invariants. Flagship relation: *lowering `amount` while holding velocity/country fixed must not change the true label* — a large score drop with unchanged true label is a **violation → fail**. Synthesizes ≥3 relations (`tasks.md` slice-6). | 1.0 | — |
| `invariant/rule` | Hard domain rules, e.g. *country_mismatch ∧ high-velocity ⇒ must be flagged regardless of amount.* Fires `fail` when the detector clears a txn violating a hard rule. | 1.0 | — |
| `differential_stub` | **Stub.** Renders a card so the slot is visible but **abstains** (weight 0, vote `"stub — not evaluated in v0"`). Honest, not faked. Later swaps to a real IsolationForest second opinion. | 0 | **"STUB"** badge |
| `llm_judge_mock` | **Deterministic mock**, no real LLM call. Votes pass/fail via a labeled heuristic with a canned-but-honest reason. | 0.5 | **"MOCK · one vote"** badge + tooltip (spec US-4) |

**Aggregator** (`modules/oracles/aggregator.py`): weighted tally per `plan.md §3`. Active v0 weights — held_out + metamorphic + invariant = 1.0 each, judge = 0.5, differential abstains. Tally + per-oracle reasons + evidence are written to `verdicts.audit_trace_json` and surfaced verbatim in the drilldown. The mock judge can never be mistaken for "the verdict": it is one labeled 0.5 vote among independent mechanisms (the core bet, constitution §3).

## 8. Dashboard (React + Vite + Tailwind + Recharts)

Lean v0 route set (subset of the eight routes in `spec.md`):

- **`/` — Run Launcher.** `n_rounds`, `batch_size`, optional `seed`; **Start** → `POST /runs`, navigate to the run view.
- **`/runs/:id` — Run view.** ASR line chart (climbing) + detection-rate line chart (falling) across rounds; the **gap tile**; a verdict table. Each tile shows the count of rows it aggregates and renders **"Not yet measured"** when empty (spec US-10).
- **`/runs/:id/verdicts/:verdictId` — Verdict drilldown.** Detector output + true label + the **five oracle vote cards** (with STUB and MOCK·one-vote badges) + the tally.

The dashboard reads the run/metrics endpoints by **polling** in v0. SSE (spec US-2) is left as a seam in `api.py` but not built unless requested.

## 9. Constitutional deviations (conscious, v0 only)

User-authorized; each honestly labeled in the UI; none introduces a fake metric.

| Constitution rule | v0 deviation | Why it's safe / reversible |
|---|---|---|
| §1 Postgres 16 (SQLite forbidden in orchestrator paths) | SQLite via `aiosqlite` | Single sequential process — the "concurrent pillar writes break SQLite" rationale does not bite yet. Same async SQLAlchemy ORM; swap to Postgres later with no model changes. |
| §1 / §5 Anthropic Opus judge | Deterministic **mock** judge | Marked "MOCK · one vote" in the UI; "no real LLM unless everything else works." |
| §1 / §5 real Kaggle data | Synthetic deterministic data | Synthetic ≠ fake: labels derived from a fixed causal rule, reproducible, honestly described. |
| §1 Modal sandbox | No sandbox | No untrusted producer code runs in v0; sandbox seam deferred. |

**Honored without compromise:** §5 "data never fake" / "no sampled or zero-defaulted metrics" — metrics come from persisted rows or render "Not yet measured"; §2 hexagonal module boundaries; §7 audit columns (`seed`, `pillar`, `created_at`) on work rows; deterministic replay.

## 10. Error handling

Constitution §8 — fail loud. Typed errors; no swallowed exceptions in business logic. A failed generator/detector/adversary marks the run `status=failed` with the typed error in `audit_trace` and the loop raises. Empty metrics is a *typed empty state* ("Not yet measured"), not an error.

## 11. Testing

Constitution §6 — 80% coverage per module; the database is **never mocked** in integration tests (constitution §8). Built test-first (`superpowers:test-driven-development`).

- **Integration:** `POST /runs` → run completes → metrics computed *from rows*; assert ASR rises across rounds and `gap > 0`. Real SQLite.
- **Determinism/replay:** same seed → byte-equal rows.
- **Adversary invariant:** every mutation preserves `true_label`; label-flipping mutations are rejected.
- **Oracle unit tests:** metamorphic relation catches the amount-lowering evasion; invariant oracle fires on country+velocity fraud; held-out oracle certifies true labels correctly.

## 12. Definition of done (v0)

- `POST /runs` launches a run that completes N rounds and persists rows.
- The dashboard renders the launcher, the run view with climbing ASR / falling detection / widening gap, and the verdict drilldown with all five oracle cards (STUB and MOCK badges present).
- `/metrics` for a run with no rows renders "Not yet measured" — never `0.0`.
- All metrics trace to persisted rows; a determinism replay reproduces byte-equal rows.
- `ruff check .` clean, `mypy --strict .` clean, `pytest` green.
