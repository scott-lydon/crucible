# Tasks

Slice-grained checklist. Each slice ends with a running platform, a passing test suite, and a single squash-merged commit on `main`. Tasks are checked off in the same commit that lands the code (the diff makes the slice auditable).

Convention: `pillar/slice-N-short-title`. Slices 0 to 4 are critical-path-sequential. Slices 5 onward fan out per `ARCHITECTURE.md` section 8. Each slice cites the `acceptance-tests.md` story it satisfies (its "Done criteria"), the `ARCHITECTURE.md` component it touches, and, through `acceptance-tests.md` section 3, the rubric line it advances. Owners are abbreviated **T** (Targets-and-Oracles), **R** (Red), **B** (Blue), **M** (Measure), **A** (all four).

## Current slice

- [ ] **slice-10-verdict-aggregator** (T). Vote tally (four oracles at 1.0, judge at 0.5, threshold 2.0), audit trace, replay determinism.

## Next slice

- [ ] **slice-11-red-search** (R). Reason then propose then query then iterate; strategy catalog persisted.

## Shared infrastructure (landed ahead of its consuming slice)

- [x] **LLM client** (`shared/llm`). `ClaudeCliClient` over the local Claude Max CLI, `ScriptedLlmClient` for MOCK_LLM, typed `LlmCallError`, cost and usage captured per call. Real CLI path proven live.
- [x] **Sandbox check runner** (`shared/sandbox/check_runner.py`). Runs assert checks against produced source in the sealed sandbox and classifies PASS / FAIL (an assertion failed) / ERROR (the check itself errored, inconclusive). Used by the held-out and metamorphic oracles so a malformed check never false-blames the producer.

## Done

- [x] **slice-9-llm-judge-oracle** (T). `LlmJudgeOracle` (Opus 4.8) reads the produced artifact, judges it against the sealed spec obligations, and returns a `{"decision","reason"}` JSON verdict parsed into a half-weight (0.5) `OracleVote`. An unparseable or empty response votes `unavailable` rather than guessing. Target-agnostic: source is read as-is, any structured output (a fraud score) is JSON-rendered first. Runs nothing in the sandbox, so no docker dependency. Registered as the fifth oracle in `wiring.py`. Live proof: real Opus passed a correct `add` and failed a subtracting one at 0.5 weight. Scripted CI covers pass / fail / unavailable / malformed-JSON / structured-artifact paths.
- [x] **slice-8-property-fuzz-oracle** (T). `PropertyFuzzOracle` has Sonnet write a `fuzz()` function that random-samples inputs and asserts spec-guaranteed properties, run in the sealed sandbox via the shared check runner. Live proof: a correct impl passes, a broken one is caught with a concrete counterexample. Uses stdlib random rather than the hypothesis library, because the no-network sandbox cannot install it (doc reconciled).
- [x] **slice-7-differential-oracle** (T, code mode). `DifferentialOracle` generates a second implementation from a different model family (Haiku) and concrete comparison inputs, runs both against the producer in the sealed sandbox, and flags disagreement without trusting either side. Live proof: a correct impl agrees on all inputs, a wrong one disagrees on 2 of 3. The fraud variant (LightGBM versus IsolationForest) is a documented follow-on.
- [x] **slice-6-metamorphic-oracle** (T). `MetamorphicOracle` has Sonnet synthesize concrete-literal metamorphic relations from the spec invariants and checks them in the sealed sandbox via the shared check runner. Live proof: real Sonnet synthesized 5 relations, passed a correct impl, caught a wrong one. `metamorphic_rules` table added. Held-out oracle refactored onto the same shared runner (now returns UNAVAILABLE rather than a false FAIL when a generated check errors).
- [x] **slice-2-fraud-target** (T). Real Kaggle creditcard model: `scripts/fetch_fraud_dataset.py` downloads the dataset, `train.py` fits LightGBM (held-out ROC-AUC 0.86, the best of the configs tried; defaults give 0.84 and more capacity gives 0.85), committed as `artifacts/fraud-v1.lgb`. `FraudTarget` scores transactions; `/health/targets/fraud` returns 200 green with checksum and AUC. Done-criterion test passes on the committed model.
- [x] **slice-5-held-out-oracle** (T). `HeldOutOracle` (Opus generates fresh asserts from the sealed spec post-submit, run against the producer output in the sealed sandbox, votes pass or fail) plus the `specs` table and server-side `SpecResolver`. Live proof: real Opus passes a correct implementation and catches a wrong one. Done-criterion test confirms a sandboxed producer cannot read `held_out_tests`. Oracle health route `/health/oracles/{name}`.
- [x] **slice-4-sealed-spec-and-sandbox** (T). `shared/sandbox` Docker runner (`--network none`, no host env) plus the seal probe. Live seal test passes: from inside the sandbox both Postgres and the internet are unreachable, so the producer cannot read the verification artifacts. The `specs` table and resolver move to slice 5 (their consumer).
- [x] **slice-3-code-agent-target** (T). `CodeAgentTarget` produces Python from a sealed spec via the LLM, scored by `ast.parse` validity; `/health/targets/{type}` self-test route; registered in wiring. Unit tests via the scripted client; live done-criterion test passes (real Claude emits ast-parseable Python).
- [x] **slice-1-target-protocol** (T). `DummyTarget` implementing the Target Protocol, `orchestrator/wiring.py` registry, `orchestrator/loop.py` driving one round end to end, persisted as an attack row. All gates green (ruff, mypy --strict on 50 files, 18 tests on real Postgres).
- [x] **slice-0-foundation** (A). Repo scaffold, value types, async Postgres persistence with Alembic, FastAPI (`POST /runs`, `GET /health`, SSE), pillar interface Protocols, module-boundary check, CI. All gates green (ruff, mypy --strict, 13 tests on real Postgres). Detail in Backlog below.

## Backlog

### Critical path (sequential)

- [x] **slice-0-foundation** (A).
  - [x] `coding-practices.md`, `ARCHITECTURE.md`, `acceptance-tests.md`, `tasks.md` at repo root, populated (no template placeholders, grep clean).
  - [x] `CONTRIBUTING.md` with squash-per-slice and shared-folder discipline.
  - [x] `design/claude-design-brief.md` ready for paste into claude.ai/design.
  - [x] `pyproject.toml` with Python 3.12, FastAPI, SQLAlchemy, Alembic, Anthropic SDK, Hypothesis, LightGBM, scikit-learn, Modal, structlog. `ruff` and `mypy --strict` configured. (Heavy ML/LLM/fuzz/sandbox deps live in optional groups so the foundation installs fast; every mandated dependency is declared.)
  - [x] `orchestrator/interfaces/{target,oracle,red,blue,measure}.py` stub Protocols. No implementations yet.
  - [x] `shared/types/`: `Attack`, `Verdict`, `AuditTrace`, `TargetSpec`, `OracleVote`, `RunId`, `AttackBudget`, `SealedSpec` (plus `Money`, `TargetOutput`, `ProbeResult`, `BluePatch`, ids, enums) as `@dataclass(frozen=True, slots=True)`.
  - [x] `shared/persistence/`: async SQLAlchemy engine, base session, Alembic `env.py`. Migrations for `runs`, `verdicts`, `attacks`, `llm_calls`, `sandbox_jobs`, `health_probes`.
  - [x] FastAPI `POST /runs`, `GET /health`, `GET /runs/:runId/stream` (SSE).
  - [x] Pre-merge check script `scripts/check_module_imports.py` that rejects `from modules.<x>` inside `modules/<y>/` and rejects commits touching `modules/` and `shared/types/` together.
  - [x] GitHub Actions workflow `.github/workflows/ci.yml` runs ruff, mypy strict, pytest, the pre-merge check script (Postgres 16 service container).
  - [x] Dual-push confirmed: `git ls-remote origin` GitHub and GitLab push URLs carry the same `feat/crucible-build` hash.
  - [x] **Done criteria:** `pytest tests/integration/test_smoke.py::test_post_runs_returns_run_id` passes; `ruff check .` clean; `mypy --strict .` clean. (13 tests pass against real Postgres; 42 files mypy-clean.)

- [x] **slice-1-target-protocol** (T).
  - [x] `interfaces.Target` Protocol with `submit(input)` and `query_target(input)` (plus `self_test`).
  - [x] `modules/targets/dummy/` concrete `DummyTarget` returning deterministic `(output, score)`.
  - [x] `orchestrator/wiring.py` registers `DummyTarget` as default for tests.
  - [x] Integration test exercises one loop round end to end with `DummyTarget` (`orchestrator/loop.py`).
  - [x] **Done criteria:** `tests/integration/test_loop_smoke.py::test_one_round_with_dummy` passes.

- [x] **slice-2-fraud-target** (T).
  - [x] `modules/targets/fraud/`: Kaggle credit-card dataset downloader (`scripts/fetch_fraud_dataset.py`), LightGBM trainer (`train.py`), serialized model committed under `artifacts/fraud-v1.lgb`, `FraudTarget` Protocol implementation.
  - [x] Self-test route `/health/targets/fraud` returns the model checksum, training timestamp, and held-out AUC.
  - [x] Integration test with real data: `tests/integration/test_fraud_target.py` (runs against the committed model, no re-download).
  - [x] **Done criteria:** model trained on real Kaggle data (284,807 rows, 492 frauds), held-out ROC-AUC 0.86 (at or above 0.85), health endpoint returns 200.

- [x] **slice-3-code-agent-target** (T).
  - [x] `modules/targets/code_agent/`: producer takes a sealed spec and returns Python source via Claude Sonnet 4.6 through the local Claude Max CLI (not the metered API).
  - [ ] Producer runs inside the sandbox: deferred to slice 4 (Docker-first) per the wiring there. Slice 3 produces source only.
  - [x] Self-test route `/health/targets/{type}` returns a fast readiness probe (client, model, and whether `claude` is on PATH). Reconciled from the original sub-second "produce hello world" round trip, which a real LLM call cannot meet and which would burn quota on every poll.
  - [x] **Done criteria:** live integration test produces real Python that compiles via `ast.parse` (`tests/integration/test_code_agent_target.py`, opt-in real CLI).

- [x] **slice-4-sealed-spec-and-sandbox** (T).
  - [x] `shared/sandbox/`: Docker job wrapper (`--network none`, no inherited env). Reconciled from Modal: Docker-first per the decision table. The sandbox executes produced code only, so full network denial replaces "egress except to Claude" (generation is orchestrator-side).
  - [x] `shared/types/sealed_spec.py`: typed `SealedSpec` value object (landed in slice 0).
  - [ ] Spec sealing via a Postgres `specs` table and server-side resolver moves to slice 5, its first consumer (the held-out oracle). The sealing SECURITY property is already enforced here by the network seal: with no network the producer cannot reach Postgres at all, credentials or not.
  - [x] "Seal Probe" under `shared/sandbox/probes/seal_probe.py` tries to reach Postgres and the internet from inside the sandbox; both must fail.
  - [x] Integration test runs the seal probe in the sandbox and asserts both unreachable, with a host positive-control proving the probe detects reachability.
  - [x] **Done criteria:** `tests/integration/test_sandbox_seal.py` passes; the in-sandbox probe returns `{"postgres_reachable": false, "internet_reachable": false}`, so a producer cannot read the spec from Postgres.

### Per-pillar (parallel after slice 4)

- [x] **slice-5-held-out-oracle** (T).
  - [x] `modules/oracles/held_out/`: Claude Opus 4.8 generates fresh asserts from the sealed spec after submission, runs them against producer output in the sealed sandbox, returns pass / fail / unavailable with reason. Plus the `specs` table and `SpecResolver` (moved here from slice 4).
  - [~] Tests persisted to `held_out_tests` table: table and model exist; the persist-then-delete-after-run lifecycle wires in at slice 10 when the loop drives oracles. The table is in place and proven unreadable from the producer.
  - [x] Self-test route `/health/oracles/{name}` exists.
  - [x] **Done criteria:** `tests/integration/test_held_out_isolation.py` confirms a sandboxed producer cannot read `held_out_tests` rows (Postgres unreachable under the seal).

- [x] **slice-6-metamorphic-oracle** (T).
  - [x] `modules/oracles/metamorphic/`: Sonnet 4.6 synthesizes metamorphic relations from spec invariants; runtime checks fire each in the sealed sandbox and report pass / fail / inconclusive. `metamorphic_rules` table added; the persist-and-render lifecycle wires in at slices 10 and 15 (same pattern as held_out_tests).
  - [x] **Done criteria:** at least three relations synthesized per spec (live: real Sonnet synthesized 5; min_rules guard enforces >= 3). Surfacing in the verdict view is the slice-15 UI wiring; the count and outcome ride the OracleVote reason now.

- [x] **slice-7-differential-oracle** (T).
  - [x] `modules/oracles/differential/`: for code, Sonnet (producer) versus Haiku (second family). Fraud variant (LightGBM versus IsolationForest) is a documented follow-on.
  - [x] Both implementations run per submission on the same inputs in the sealed sandbox; outputs compared.
  - [x] **Done criteria:** disagreement count measured (live: 2 of 3 inputs on a wrong impl, 0 on a correct one); the platform flags disagreement without trusting a single side as ground truth.

- [x] **slice-8-property-fuzz-oracle** (T).
  - [x] `modules/oracles/property_fuzz/`: Sonnet writes a `fuzz()` function that random-samples inputs (stdlib `random`, since the no-network sandbox cannot install `hypothesis`) and asserts spec invariants; runs in the sealed sandbox.
  - [x] **Done criteria:** the fuzzer finds at least one violation on a deliberately broken producer (live: a concrete counterexample), and the scripted test reproduces it in CI.

- [x] **slice-9-llm-judge-oracle** (T).
  - [x] `modules/oracles/llm_judge/`: Opus 4.8 reads output and votes pass / fail with one-paragraph reason. Parses a `{"decision","reason"}` JSON verdict; an unparseable or empty response votes `unavailable`, never a guessed pass or fail.
  - [x] Judge gets 0.5 vote weight per `ARCHITECTURE.md` section 3. Registered in `orchestrator/wiring.py` as the fifth oracle.
  - [~] Verdict view marks the judge card "one vote" with the tooltip from `acceptance-tests.md` US-4. The 0.5 weight rides the `OracleVote` now; the card and tooltip are the slice-15 UI wiring (same pattern as the other oracle cards).

- [ ] **slice-10-verdict-aggregator** (T).
  - [ ] `modules/oracles/aggregator.py`: vote tally per `ARCHITECTURE.md` section 3.
  - [ ] Audit trace JSON written to `verdicts.audit_trace`.
  - [ ] Replay determinism: seed capture on every oracle's row.
  - [ ] **Done criteria:** integration test replays a past verdict and asserts byte-equal output.

- [ ] **slice-11-red-search** (R).
  - [ ] `modules/red/search.py`: reason → propose → query → iterate using Sonnet 4.6.
  - [ ] `modules/red/catalog.py`: strategy catalog persisted to Postgres + JSONL append-only log.
  - [ ] **Done criteria:** red agent finds at least three distinct evasion or reward-hack strategies in the test fixtures, all surface in `/catalog`.

- [ ] **slice-12-white-box-mode** (R).
  - [ ] `modules/red/white_box.py`: prompt includes oracle protocol descriptions; runs on every pass after slices 5 to 10 land.
  - [ ] Dashboard renders black-box and white-box catch rate side by side at `/metrics`.
  - [ ] **Done criteria:** white-box catch rate is at most the black-box rate (sanity), and the gap is reported.

- [ ] **slice-13-red-hybrid-fallback** (R).
  - [ ] `modules/red/hybrid.py`: LLM proposes strategy, `scipy.optimize` executes when constraint satisfaction by LLM alone fails.
  - [ ] **Done criteria:** test scenario where pure LLM search fails three rounds in a row triggers fallback automatically.

- [ ] **slice-14-blue-loop** (B).
  - [ ] `modules/blue/proposer.py`: reads catalog, proposes features / samples / ensemble via Sonnet 4.6.
  - [ ] `modules/blue/retrainer.py`: applies the patch. For the fraud target it runs LightGBM training and emits `artifacts/fraud-vN.lgb` at the next version integer. For the code-agent target it applies the prompt-and-configuration diff and emits a new `agent_configs` row; the vendor language model is never touched.
  - [ ] `modules/blue/holdout_validator.py`: held-out attack set defined up front, never overlaps patch training attacks.
  - [ ] **Done criteria:** one blue round against the fraud target retrains the LightGBM classifier and detection rate measurably recovers on held-out attacks; one blue round against the code-agent target writes a reviewable prompt-and-configuration diff and held-out detection recovers.

- [ ] **slice-15-dashboard-spa** (M).
  - [ ] `dashboard/`: Vite + React 18 + Tailwind + Recharts + React Router 6 scaffold.
  - [ ] Routes: `/`, `/runs/:runId`, `/runs/:runId/verdicts/:verdictId`, `/catalog`, `/metrics`, `/blue/:patchId`, `/health`, `/admin/debug`.
  - [ ] SSE client wired to `/runs/:runId/stream`.
  - [ ] **Done criteria:** all seven mandatory routes render without error; SSE updates ASR chart live.

- [ ] **slice-16-corpus-export** (M).
  - [ ] `modules/measure/corpus_exporter.py`: JSONL streamer of successful attacks.
  - [ ] `/corpus` route shows the table and the download button.
  - [ ] **Done criteria:** downloaded JSONL row count equals table row count exactly.

- [ ] **slice-17-risk-report** (M).
  - [ ] `modules/measure/risk_report.py`: SR 11-7 sections rendered from real run state, every numeric field linked to its Postgres row identifier.
  - [ ] Markdown and PDF generation.
  - [ ] **Done criteria:** report renders for a real run; clicking any number jumps to the source row.

- [ ] **slice-18-halt-cert** (M).
  - [ ] `modules/measure/halt_rule.py`: Postgres `halted=true` flag set when white-box recall below threshold (default 0.7, configurable).
  - [ ] Orchestrator refuses new run launches with HTTP 409 and a typed error body.
  - [ ] Dashboard banner appears on every route.
  - [ ] **Done criteria:** deliberately drop recall and verify the banner and the 409.

- [ ] **slice-19-demo-polish** (A).
  - [ ] 10-minute runbook at `docs/DEFENSE_BREAKOUT_SCRIPT.md`.
  - [ ] `AI_INTERVIEW_PREP.md` populated against `acceptance-tests.md` rubric mapping.
  - [ ] Architecture website `website/index.html` updated for the as-built numbers.
  - [ ] Render deployment verified end to end (built, deployed, restarted, behavior confirmed live).

### Stretch (only after slice 19 lands clean)

- [ ] **stretch-co-evolution-curve**. Plot ASR versus detection over N rounds at `/co-evolution`.
- [ ] **stretch-time-series-target**. Add autoencoder, GMM, or DAGMM for time-series anomaly detection.
- [ ] **stretch-research-agent-target**. Promote the stub to a real implementation.
- [ ] **stretch-verifier-tournament**. Cheapest-verifier router, hierarchical decomposition, debate escalation, live human-review-budget meter.
- [ ] **stretch-submission-portal**. Producer login, billing layer, producer-scoped permissions.
