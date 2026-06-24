# Crucible — interview prep, rubric-mapped

Maps each `acceptance-tests.md` section-3 rubric dimension to the as-built
evidence: the user story, the code that satisfies it, and the test that proves it.

## Architecture (US-1, US-7, US-9, US-14)

- **Hexagonal boundaries.** `orchestrator/interfaces/` holds the five pillar
  Protocols; `modules/<pillar>/` implement them; `orchestrator/wiring.py` is the
  only place a concrete class meets its interface. A pre-merge check
  (`scripts/check_module_imports.py`) rejects cross-module imports and any commit
  that co-edits `shared/types/` with `modules/`.
- **White-box self-test every pass (US-14).** `orchestrator/loop.py` runs a
  black-box then a white-box red pass; `modules/red/white_box.py` injects the
  disclosed oracle scheme and pins the informed pass to Opus 4.8. `/metrics` shows
  both catch rates and the gap (the report card). Proof: `test_metrics.py`,
  `test_white_box_live.py` (live, opt-in).
- **Blue patch review (US-7).** `modules/blue/` proposes, retrains, and validates
  on a held-out attack set that must not overlap training (typed
  `HoldoutContamination`). `/blue/:patchId` renders it. Proof:
  `test_blue_fraud_recovery.py` (real Kaggle retrain → recovery).

## Scalability (US-2, US-5, US-8)

- **SSE per-row streaming (US-2).** `/runs/:id/stream` emits each persisted attack
  and verdict; the dashboard ASR readout updates live. Proof:
  `test_dashboard_routes.py::test_sse_streams_persisted_rows`.
- **Sealed sandbox (US-5).** `shared/sandbox/` runs produced code with
  `--network none` and no host env; the seal probe proves Postgres and the
  internet are unreachable from inside. Proof: `test_sandbox_seal.py`.
- **Self-tests (US-8).** `/health`, `/health/targets/{type}`, `/health/oracles/{name}`.

## Security (US-9, US-13, US-14)

- **Spec sealing.** The producer sandbox has no network, so it cannot read the
  spec or the held-out tests from Postgres. Proof: `test_held_out_isolation.py`.
- **Halt at the red line (US-13).** `modules/measure/halt_rule.py` sets the
  persisted halt flag when white-box recall falls below 0.70; `POST /runs` returns
  409 and the banner appears on every route. Proof: `test_halt.py`.
- **Catch rate is recall against an informed attacker (US-14).** The headline
  number is white-box, never black-box.

## Testing (US-3, US-4, US-5, US-8, US-10)

- **No mocked database.** Every integration test runs against real Postgres
  (`tests/conftest.py`); the LLM is the only doubled boundary, and the live path
  is proven by opt-in tests against the real Claude CLI.
- **Non-colluding oracles (US-4).** Four mechanical oracles at weight 1.0 plus the
  LLM judge at 0.5; the aggregator passes at a 2.0 threshold. Replay is byte-equal
  (`test_verdict_replay.py`).
- **Honest metrics (US-10).** A tile with zero contributing runs reports
  "not yet measured", never a sampled 0.0.

## The three questions to expect

1. *Why is the white-box gap the headline?* Because a black-box catch rate is
   borrowed from the attacker's ignorance; the gap measures how much.
2. *How do you know an oracle didn't collude?* They fail differently (held-out
   asserts, metamorphic relations, a second-family differential, property fuzz, an
   independent judge) and an `UNAVAILABLE` oracle contributes nothing rather than
   guessing.
3. *What does Crucible certify?* Nothing. It reports a catch rate against an
   informed adversary and halts when that recall drops below the red line.

## As-built numbers

- Fraud model: real Kaggle credit-card LightGBM, held-out ROC-AUC 0.86.
- Test suite: 134 passing, 7 opt-in live/slow skipped, real Postgres.
- Pillars: targets + oracles, red (search, white-box, hybrid, catalog), blue
  (proposer, retrainer, held-out validator), measure (metrics, corpus, SR 11-7
  report, halt).
