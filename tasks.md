# Tasks

Slice-grained checklist. Each slice ends with a running platform, a passing `vouch` report, and a single squash-merged commit on `main`. Tasks are checked off in the same commit that lands the code (the diff makes the slice auditable).

Convention: `pillar/slice-N-short-title`. Slices 0 to 4 are critical-path-sequential. Slices 5 onward fan out per `ARCHITECTURE.md` section 8. Each slice cites the `acceptance-tests.md` story it satisfies (its "Done criteria"), the `ARCHITECTURE.md` component it touches, and, through `acceptance-tests.md` section 5, the rubric line it advances. Owners are abbreviated **T** (Targets-and-Oracles), **R** (Red), **B** (Blue), **M** (Measure), **A** (all four).

## Current slice

- [ ] **slice-0-foundation** (A). The CATA docs (this file plus `coding-practices.md`, `ARCHITECTURE.md`, `acceptance-tests.md`) and `QA_ADVERSARY.md`, repo scaffolding, Continuous Integration (CI) skeleton.

## Next slice

- [ ] **slice-1-target-protocol** (T). `interfaces.Target` Protocol, `DummyTarget`, end-to-end smoke through the orchestrator loop.

## Backlog

### Critical path (sequential)

- [ ] **slice-0-foundation** (A).
  - [x] `coding-practices.md`, `ARCHITECTURE.md`, `acceptance-tests.md`, `tasks.md`, `QA_ADVERSARY.md` at repo root, populated (no template placeholders, grep clean).
  - [x] `CONTRIBUTING.md` with squash-per-slice and shared-folder discipline.
  - [x] `design/claude-design-brief.md` ready for paste into claude.ai/design.
  - [ ] `pyproject.toml` with `python = "^3.12"`, FastAPI, SQLAlchemy, Alembic, Anthropic SDK, Hypothesis, LightGBM, scikit-learn, Modal, structlog. `ruff` and `mypy --strict` configured.
  - [ ] `orchestrator/interfaces/{target,oracle,red,blue,measure}.py` stub Protocols. No implementations yet.
  - [ ] `shared/types/`: `Attack`, `Verdict`, `AuditTrace`, `TargetSpec`, `OracleVote`, `RunId`, `AttackBudget`, `SealedSpec` as `@dataclass(frozen=True, slots=True)`.
  - [ ] `shared/persistence/`: async SQLAlchemy engine, base session, Alembic `env.py`. Migrations for `runs`, `verdicts`, `attacks`, `llm_calls`, `sandbox_jobs`, `health_probes`.
  - [ ] FastAPI `POST /runs`, `GET /health`, `GET /runs/:runId/stream` (SSE).
  - [ ] Pre-merge check script `scripts/check_module_imports.py` that rejects `from modules.<x>` inside `modules/<y>/` and rejects pull requests touching `modules/` and `shared/types/` together.
  - [ ] GitHub Actions workflow `.github/workflows/ci.yml` runs ruff, mypy strict, pytest, the pre-merge check script.
  - [ ] Dual-push confirmed: `git ls-remote https://github.com/scott-lydon/crucible.git main` equals `git ls-remote gitlab main`.
  - [ ] **Done criteria for `vouch`:** `pytest tests/integration/test_smoke.py::test_post_runs_returns_run_id` passes; `ruff check .` clean; `mypy --strict .` clean.

- [ ] **slice-1-target-protocol** (T).
  - [ ] `interfaces.Target` Protocol with `submit(input)` and `query_target(input)`.
  - [ ] `modules/targets/dummy/` concrete `DummyTarget` returning canned `(output, score)`.
  - [ ] `orchestrator/wiring.py` registers `DummyTarget` as default for tests.
  - [ ] Integration test exercises one loop round end to end with `DummyTarget`.
  - [ ] **Done criteria for `vouch`:** `tests/integration/test_loop_smoke.py::test_one_round_with_dummy` passes.

- [ ] **slice-2-fraud-target** (T).
  - [ ] `modules/targets/fraud/`: Kaggle credit-card dataset downloader (`scripts/fetch_fraud_dataset.py`), LightGBM trainer (`train.py`), serialized model under `artifacts/fraud-v1.lgb`, `FraudTarget` Protocol implementation.
  - [ ] Self-test endpoint `/health/targets/fraud` returns model file checksum and last training timestamp.
  - [ ] Integration test with real data: `pytest tests/integration/test_fraud_target.py`.
  - [ ] **Done criteria for `vouch`:** model trained on real Kaggle data (not a stub), AUC against the held-out portion at or above 0.85, health endpoint returns 200.

- [ ] **slice-3-code-agent-target** (T).
  - [ ] `modules/targets/code_agent/`: producer that takes a sealed `code_spec.yaml` and returns Python source via Claude Sonnet 4.6 tool use.
  - [ ] Producer runs inside the Modal sandbox (per slice 4 wiring).
  - [ ] Self-test endpoint `/health/targets/code_agent` runs a "produce hello world" round trip in under one second.
  - [ ] **Done criteria for `vouch`:** integration test produces real Python code that compiles via `ast.parse`.

- [ ] **slice-4-sealed-spec-and-sandbox** (T).
  - [ ] `shared/sandbox/`: Modal job wrapper. Strips env vars, denies network egress except to Claude.
  - [ ] `shared/types/sealed_spec.py`: typed `SealedSpec` value object.
  - [ ] Spec sealing: spec stored in Postgres `specs` table, read by oracles through a server-side resolver. Producer container has no Postgres credentials.
  - [ ] "Seal Probe" fixture under `shared/sandbox/probes/` that, from inside the sandbox, tries to reach Postgres, Modal control plane, and the verification bucket. All three must time out.
  - [ ] Integration test runs the seal probe and asserts all three probes failed.
  - [ ] **Done criteria for `vouch`:** `tests/integration/test_sandbox_seal.py` passes; the test for "producer can read the spec from Postgres directly" fails as expected.

### Per-pillar (parallel after slice 4)

- [ ] **slice-5-held-out-oracle** (T).
  - [ ] `modules/oracles/held_out/`: Claude Opus 4.8 generates fresh tests from the sealed spec after submission, runs them against producer output, returns pass / fail with reason.
  - [ ] Tests are persisted to `held_out_tests` table, deleted after the run completes.
  - [ ] Self-test endpoint exists.
  - [ ] **Done criteria for `vouch`:** integration test confirms the producer cannot read `held_out_tests` rows.

- [ ] **slice-6-metamorphic-oracle** (T).
  - [ ] `modules/oracles/metamorphic/`: Sonnet 4.6 synthesizes metamorphic rules from spec invariants; rules persisted to `metamorphic_rules`; runtime checks fire each rule and report pass / fail.
  - [ ] **Done criteria for `vouch`:** at least three metamorphic rules synthesized per spec, all surface in the dashboard verdict view.

- [ ] **slice-7-differential-oracle** (T).
  - [ ] `modules/oracles/differential/`: for fraud, LightGBM versus IsolationForest; for code, Sonnet versus Haiku.
  - [ ] Both implementations are spawned per submission, outputs compared.
  - [ ] **Done criteria for `vouch`:** disagreement rate measured on the test fixtures; the platform never trusts a single side as ground truth.

- [ ] **slice-8-property-fuzz-oracle** (T).
  - [ ] `modules/oracles/property_fuzz/`: `hypothesis` strategies derived from spec invariants.
  - [ ] **Done criteria for `vouch`:** fuzz suite finds at least one violation on a deliberately broken producer in CI.

- [ ] **slice-9-llm-judge-oracle** (T).
  - [ ] `modules/oracles/llm_judge/`: Opus 4.8 reads output and votes pass / fail with one-paragraph reason.
  - [ ] Judge gets 0.5 vote weight per `ARCHITECTURE.md` section 3.
  - [ ] Verdict view marks the judge card "one vote" with the tooltip from `acceptance-tests.md` US-4.

- [ ] **slice-10-verdict-aggregator** (T).
  - [ ] `modules/oracles/aggregator.py`: vote tally per `ARCHITECTURE.md` section 3.
  - [ ] Audit trace JSON written to `verdicts.audit_trace`.
  - [ ] Replay determinism: seed capture on every oracle's row.
  - [ ] **Done criteria for `vouch`:** integration test replays a past verdict and asserts byte-equal output.

- [ ] **slice-11-red-search** (R).
  - [ ] `modules/red/search.py`: reason → propose → query → iterate using Sonnet 4.6.
  - [ ] `modules/red/catalog.py`: strategy catalog persisted to Postgres + JSONL append-only log.
  - [ ] **Done criteria for `vouch`:** red agent finds at least three distinct evasion or reward-hack strategies in the test fixtures, all surface in `/catalog`.

- [ ] **slice-12-white-box-mode** (R).
  - [ ] `modules/red/white_box.py`: prompt includes oracle protocol descriptions; runs on every pass after slices 5 to 10 land.
  - [ ] Dashboard renders black-box and white-box catch rate side by side at `/metrics`.
  - [ ] **Done criteria for `vouch`:** white-box catch rate is at most the black-box rate (sanity), and the gap is reported.

- [ ] **slice-13-red-hybrid-fallback** (R).
  - [ ] `modules/red/hybrid.py`: LLM proposes strategy, `scipy.optimize` executes when constraint satisfaction by LLM alone fails.
  - [ ] **Done criteria for `vouch`:** test scenario where pure LLM search fails three rounds in a row triggers fallback automatically.

- [ ] **slice-14-blue-loop** (B).
  - [ ] `modules/blue/proposer.py`: reads catalog, proposes features / samples / ensemble via Sonnet 4.6.
  - [ ] `modules/blue/retrainer.py`: applies the patch. For the fraud target it runs LightGBM training and emits `artifacts/fraud-vN.lgb` at the next version integer. For the code-agent target it applies the prompt-and-configuration diff and emits a new `agent_configs` row; the vendor language model is never touched.
  - [ ] `modules/blue/holdout_validator.py`: held-out attack set defined up front, never overlaps patch training attacks.
  - [ ] **Done criteria for `vouch`:** one blue round against the fraud target retrains the LightGBM classifier and detection rate measurably recovers on held-out attacks; one blue round against the code-agent target writes a reviewable prompt-and-configuration diff and held-out detection recovers.

- [ ] **slice-15-dashboard-spa** (M).
  - [ ] `dashboard/`: Vite + React 18 + Tailwind + Recharts + React Router 6 scaffold.
  - [ ] Routes: `/`, `/runs/:runId`, `/runs/:runId/verdicts/:verdictId`, `/catalog`, `/metrics`, `/blue/:patchId`, `/health`, `/admin/debug`.
  - [ ] SSE client wired to `/runs/:runId/stream`.
  - [ ] **Done criteria for `vouch`:** all seven mandatory routes render without error; SSE updates ASR chart live.

- [ ] **slice-16-corpus-export** (M).
  - [ ] `modules/measure/corpus_exporter.py`: JSONL streamer of successful attacks.
  - [ ] `/corpus` route shows the table and the download button.
  - [ ] **Done criteria for `vouch`:** downloaded JSONL row count equals table row count exactly.

- [ ] **slice-17-risk-report** (M).
  - [ ] `modules/measure/risk_report.py`: SR 11-7 sections rendered from real run state, every numeric field linked to its Postgres row identifier.
  - [ ] Markdown and PDF generation.
  - [ ] **Done criteria for `vouch`:** report renders for a real run; clicking any number jumps to the source row.

- [ ] **slice-18-halt-cert** (M).
  - [ ] `modules/measure/halt_rule.py`: Postgres `halted=true` flag set when white-box recall below threshold (default 0.7, configurable).
  - [ ] Orchestrator refuses new run launches with HTTP 409 and a typed error body.
  - [ ] Dashboard banner appears on every route.
  - [ ] **Done criteria for `vouch`:** deliberately drop recall and verify the banner and the 409.

- [ ] **slice-19-demo-polish** (A).
  - [ ] 10-minute runbook at `docs/DEFENSE_BREAKOUT_SCRIPT.md`.
  - [ ] `AI_INTERVIEW_PREP.md` populated against `acceptance-tests.md` rubric mapping.
  - [ ] Architecture website `website/index.html` updated for the as-built numbers.
  - [ ] Render deployment verified end to end per the global CLAUDE.md "DEPLOY-VERIFY-OR-DIE" checklist.

### Stretch (only after slice 19 lands clean)

- [ ] **stretch-co-evolution-curve**. Plot ASR versus detection over N rounds at `/co-evolution`.
- [ ] **stretch-time-series-target**. Add autoencoder, GMM, or DAGMM for time-series anomaly detection.
- [ ] **stretch-research-agent-target**. Promote the stub to a real implementation.
- [ ] **stretch-verifier-tournament**. Cheapest-verifier router, hierarchical decomposition, debate escalation, live human-review-budget meter.
- [ ] **stretch-submission-portal**. Producer login, billing layer, producer-scoped permissions.
