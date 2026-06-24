# Tasks

Slice-grained checklist. Each slice ends with a running platform, a passing test suite, and a single squash-merged commit on `main`. Tasks are checked off in the same commit that lands the code (the diff makes the slice auditable).

Convention: `pillar/slice-N-short-title`. Slices 0 to 4 are critical-path-sequential. Slices 5 onward fan out per `ARCHITECTURE.md` section 8. Each slice cites the `acceptance-tests.md` story it satisfies (its "Done criteria"), the `ARCHITECTURE.md` component it touches, and, through `acceptance-tests.md` section 3, the rubric line it advances. Owners are abbreviated **T** (Targets-and-Oracles), **R** (Red), **B** (Blue), **M** (Measure), **A** (all four).

## Current slice

- [ ] **slice-0-foundation** (A). The core docs (this file plus `coding-practices.md`, `ARCHITECTURE.md`, `acceptance-tests.md`), repo scaffolding, Continuous Integration (CI) skeleton. PARTIALLY DONE: docs + Protocols + types + persistence + FastAPI + import-check script all built; SSE stream, Alembic migrations, and CI/dual-push automation NOT yet (see sub-items).

## Next slice

- [ ] **slice-1-target-protocol** (T). `interfaces.Target` Protocol, `DummyTarget`, end-to-end smoke through the orchestrator loop. NOT DONE as written: we never built a `DummyTarget`; the loop is smoke-tested against the offline synthetic victim (`examples/targets/fraud_synth`) and the real Sparkov victim instead. The generic `Detector`/`Adversary`/`Oracle` Protocols this slice intended do exist (`orchestrator/interfaces/`).

## Backlog

### Critical path (sequential)

- [ ] **slice-0-foundation** (A).
  - [x] `coding-practices.md`, `ARCHITECTURE.md`, `acceptance-tests.md`, `tasks.md` at repo root, populated (no template placeholders, grep clean).
  - [x] `CONTRIBUTING.md` with squash-per-slice and shared-folder discipline.
  - [x] `design/claude-design-brief.md` ready for paste into claude.ai/design.
  - [ ] `pyproject.toml` with `python = "^3.12"`, FastAPI, SQLAlchemy, Alembic, Anthropic SDK, Hypothesis, LightGBM, scikit-learn, (sandbox: Docker via the docker CLI; Modal optional), structlog. `ruff` and `mypy --strict` configured.
  - [ ] `orchestrator/interfaces/{target,oracle,red,blue,measure}.py` stub Protocols. No implementations yet.
  - [ ] `shared/types/`: `Attack`, `Verdict`, `AuditTrace`, `TargetSpec`, `OracleVote`, `RunId`, `AttackBudget`, `SealedSpec` as `@dataclass(frozen=True, slots=True)`.
  - [ ] `shared/persistence/`: async SQLAlchemy engine, base session, Alembic `env.py`. Migrations for `runs`, `verdicts`, `attacks`, `llm_calls`, `sandbox_jobs`, `health_probes`.
  - [ ] FastAPI `POST /runs`, `GET /health`, `GET /runs/:runId/stream` (SSE).
  - [ ] Pre-merge check script `scripts/check_module_imports.py` that rejects `from modules.<x>` inside `modules/<y>/` and rejects pull requests touching `modules/` and `shared/types/` together.
  - [ ] GitHub Actions workflow `.github/workflows/ci.yml` runs ruff, mypy strict, pytest, the pre-merge check script.
  - [ ] Dual-push confirmed: `git ls-remote https://github.com/scott-lydon/crucible.git main` equals `git ls-remote gitlab main`.
  - [ ] **Done criteria:** `pytest tests/integration/test_smoke.py::test_post_runs_returns_run_id` passes; `ruff check .` clean; `mypy --strict .` clean.

- [ ] **slice-1-target-protocol** (T). NOT DONE as written (no `DummyTarget`); the generic Protocols exist and the loop is smoke-tested against real/synth victims instead.
  - [x] `interfaces` Protocols (`Detector`/`Adversary`/`Oracle` in `orchestrator/interfaces/`) — the target-agnostic surface this slice intended.
  - [ ] `modules/targets/dummy/` concrete `DummyTarget` returning canned `(output, score)`. NOT BUILT — superseded by the offline synthetic victim.
  - [x] `orchestrator/wiring.py` is the composition root; it registers the offline synth victim (`build_components`) used by the smoke/health path.
  - [x] Integration test exercises one loop round end to end (against the synth victim, not a `DummyTarget`).
  - [ ] **Done criteria:** the literal `test_one_round_with_dummy` was never written; equivalent loop smoke runs on the synth victim.

- [x] **slice-2-fraud-target** (T). DONE — but pivoted from Kaggle credit-card to the REAL Sparkov dataset (`examples/targets/fraud_sparkov`), trained, checksum-verified, behind the generic `LocalModelTarget`. Text updated to as-built.
  - [x] `examples/targets/fraud_sparkov/`: real Sparkov dataset loader (`loader.py`, checksum-gated), LightGBM trainer (`train.py`), serialized model under `artifacts/sparkov_flawed.pkl`, scored via the generic `LocalModelTarget` (`modules/targets/local_model`). Deliberately amt-reliant (the exploitable blind spot).
  - [x] `/health` introspects the detector/oracle component shapes; the Sparkov artifact is checksum-verified at load.
  - [x] Integration tests with real data (skip-if-absent): `tests/integration/test_sparkov_loop.py`, `tests/integration/test_sparkov_differential.py`.
  - [x] **Done criteria:** model trained on real Sparkov data (not a stub). NOTE: the detector is INTENTIONALLY flawed (amt-only), so a high AUC is NOT a goal — the declared rule is a deliberate proxy (see README precision caveat); the harness measures recall loss vs the spec, not catch rate.

- [ ] **slice-3-code-agent-target** (T). NOT BUILT. The code-agent producer target was not implemented for v0; only the fraud (Sparkov) target ships. Tracked for the second-target generalization.
  - [ ] `examples/targets/code_agent/`: producer that takes a sealed `code_spec.yaml` and returns Python source via Claude tool use. NOT BUILT.
  - [ ] Producer runs inside the sandbox adapter. NOT BUILT.
  - [ ] Self-test endpoint for code_agent. NOT BUILT.
  - [ ] **Done criteria:** not met (slice not started).

- [x] **slice-4-sealed-spec-and-sandbox** (T). DONE.
  - [x] `shared/sandbox/`: sandbox adapter port + local Docker adapter (`LocalDockerSandbox`). Strips env, `--network none` denies egress.
  - [x] `shared/types/sealed_spec.py`: typed `SealedSpec` value object (+ `from_dict`/`to_dict`/`from_yaml` boundary loaders).
  - [x] Spec sealing: spec stored in Postgres `specs` table (`repo.store_spec`), read back via a server-side resolver (`repo.resolve_spec`). The live run now RESOLVES the spec server-side (`orchestrator/api.py`) so the harness/oracles drive off the resolved spec; the producer container has no DB creds.
  - [x] "Seal Probe" fixture under `shared/sandbox/probes/seal_probe.py` that, from inside the sandbox, tries Postgres / host control plane / verification target — all must fail.
  - [x] Integration test runs the seal probe and asserts all three failed, with a positive control (anti-tautology).
  - [x] **Done criteria:** `tests/integration/test_sandbox_seal.py` passes (Docker-gated); the "producer reads the spec from Postgres directly" negative control fails as expected.

### Per-pillar (parallel after slice 4)

- [x] **slice-5-held-out-oracle** (T). DONE — as-built is a SealedSpec-driven independent label authority, not a per-run `held_out_tests` table.
  - [x] `modules/oracles/held_out/`: an independent held-out label authority certifies each sample's ground-truth label from the sealed rule (injected `label_fn`) and FAILS the detector when it cleared a true positive. `describe()` exposes only the MECHANISM (never the literal rule), so a white-box red agent can't trivially flip the label.
  - [x] No `held_out_tests` table: ground truth is recomputed from the sealed rule per sample (simpler, equivalent for v0). The spec itself is sealed in Postgres and unreachable from the producer sandbox (slice-4).
  - [x] Self-test: the oracle's shape is introspected by `/health`.
  - [x] **Done criteria:** the producer is sandboxed and cannot reach the verification store (proven by `test_sandbox_seal.py`); the held-out label is never exposed to the producer.

- [x] **slice-6-metamorphic-oracle** (T). DONE — SealedSpec-driven, evaluated from the spec's declared metamorphic relations (no separate `metamorphic_rules` table; rules ARE the spec data).
  - [x] `modules/oracles/metamorphic/`: reads the spec's metamorphic relations; R1 fails a label-preserving mutation that dropped the score materially on a still-positive sample, R2 fails any still-positive sample the detector cleared. Verdicts surface in the dashboard verdict view.
  - [x] **Done criteria:** the Sparkov spec declares the `amt_decrease_label_invariance` relation the oracle evaluates; metamorphic FAIL votes surface per verdict. (Rules are declared as spec DATA rather than synthesized, so the "three synthesized rules" wording is updated to "evaluated from declared relations".)

- [x] **slice-7-differential-oracle** (T). DONE.
  - [x] `modules/oracles/differential/`: for the Sparkov fraud target, the LightGBM detector vs a REAL cross-family sklearn IsolationForest (`fraud_sparkov.isoforest_is_fraud`) trained over a richer feature set incl. the `hour` the target ignores. (Code-target Sonnet-vs-Haiku path not built — code target not shipped.)
  - [x] The second opinion is genuine: it flags a night-hour low-amount fraud the amt-reliant target clears.
  - [x] **Done criteria:** `tests/integration/test_sparkov_differential.py` proves the cross-family disagreement becomes a FAIL vote; neither side is trusted as sole ground truth (the harness aggregates).

- [x] **slice-8-property-fuzz-oracle** (T). DONE.
  - [x] `modules/oracles/property_fuzz/`: a generative Hypothesis search (ZERO LLM) for an input satisfying a declared `must_flag_when` invariant the detector clears. Seeded/deterministic, run-level probe.
  - [x] **Done criteria:** the fuzzer FAILS the REAL Sparkov detector — the `night_hour_must_flag` invariant (the detector's documented amt-reliant blind spot) yields a generated night-hour low-amount counterexample the detector clears (`tests/integration/test_sparkov_property_fuzz.py`, skip-if-data/artifact-absent).

- [x] **slice-9-llm-judge-oracle** (T). DONE.
  - [x] `modules/oracles/llm_judge/`: REAL Opus 4.8 reads the output and votes pass/fail with a one-paragraph reason; budgeted (`max_calls`) and abstains honestly when over budget. Tests inject a `MockProvider` (ZERO real calls).
  - [x] Vote weight per `ARCHITECTURE.md` §3; the verdict view marks the judge card as the LLM vote (`is_llm`).
  - [x] Verdict view renders the judge card with its reason.

- [x] **slice-10-verdict-aggregator** (T). DONE.
  - [x] `modules/oracles/aggregator.py`: vote tally per `ARCHITECTURE.md` §3, persisted as `VerdictRow`/`OracleVoteRow` (aggregate_pass + fail_weight, per-oracle reason/evidence).
  - [x] Audit trail: each oracle's vote + evidence persisted per verdict and exposed at `/runs/{id}/verdicts/{verdictId}`.
  - [x] Determinism: seed captured on the run; the non-LLM oracles are deterministic.
  - [x] **Done criteria:** aggregation + per-vote persistence covered by `modules/oracles/test_oracles.py` and the full-run API test.

- [x] **slice-11-red-search** (R). DONE.
  - [x] `modules/red/llm_red/agent.py`: reason → propose → query → iterate using Sonnet 4.6 (constitution §1), budgeted; the deterministic mutator is the free fallback.
  - [x] `modules/red/catalog.py`: strategy catalog persisted (Postgres) + surfaced; covered by `modules/red/test_catalog.py`.
  - [x] **Done criteria:** the catalog records distinct evasion strategies the red loop lands; exercised in the catalog + loop tests.

- [x] **slice-12-white-box-mode** (R). DONE.
  - [x] `modules/red/white_box.py`: the prompt carries the oracles' verification SCHEME (each oracle's `describe()` assembled by `modules/oracles/scheme.py`), with the same free deterministic fallback; runs as a pass after the black-box arc. Opus 4.8 (constitution §1: white-box self-test on the higher tier).
  - [x] Dashboard renders black-box vs white-box catch rate + the gap at `/metrics` (nested `white_box` object).
  - [x] **Done criteria:** white-box catch rate ≤ black-box (sanity) and the gap is reported (`tests/integration/test_white_box_pass.py`).

- [x] **slice-13-red-hybrid-fallback** (R). DONE — fallback is the FREE deterministic metamorphic mutator, not `scipy.optimize`.
  - [x] `modules/red/hybrid/adversary.py`: the LLM red agent proposes; when it returns nothing (or is over budget), the deterministic metamorphic mutator drives the loop automatically — keeping co-evolution alive while bounding spend.
  - [x] **Done criteria:** `modules/red/hybrid/test_adversary.py` proves the deterministic fallback fires automatically when the primary yields nothing. (We use the deterministic mutator rather than `scipy.optimize`; text updated to as-built.)

- [x] **slice-14-blue-loop** (B). DONE — Option B: a genuine code-engineering maker (no feature menu).
  - [x] `modules/blue/code_engineer.py`: the maker gets ONLY the RAW Sparkov CSV columns (no derived `hour`/`distance` menu) and must DISCOVER the missing signal by WRITING a feature-engineering transform (Opus 4.8 — documented §1 deviation for blue CODE generation). The transform runs in the locked-down `LocalDockerSandbox`, then the harness retrains and iterates.
  - [x] `modules/blue/loop.py` + `examples/targets/fraud_sparkov/raw_surface.py` (`retrain_with_engineered`): retrain LightGBM on base features + the engineered column, emit a versioned artifact, re-score the holdout.
  - [x] `modules/blue/validator.py`: the held-out evasion set (real night-frauds with amt lowered) is defined up front and validated against the REAL committed label, separate from training.
  - [x] **Done criteria:** one blue round retrains and detection recovers on the held-out attacks (`tests/integration/test_full_run_api.py`, `tests/integration/test_blue_recovery.py`). The code-agent half is N/A (code target not shipped).

- [x] **slice-15-dashboard-spa** (M). DONE.
  - [x] `dashboard/`: Vite + React + Tailwind + React Router scaffold.
  - [x] Routes: `/`, `/runs/:id`, `/runs/:id/verdicts/:vid`, `/catalog`, `/metrics`, `/blue/:patchId`, `/health`, `/admin/debug` (8 routes, incl. the 7 mandatory ones).
  - [x] SSE client wired to `/runs/:id/stream`.
  - [x] **Done criteria:** routes render (covered by `dashboard/src/routes/routes.test.tsx`); SSE drives the live view.

- [x] **slice-16-corpus-export** (M). DONE.
  - [x] `modules/measure/corpus_exporter.py`: JSONL streamer of successful evasions.
  - [x] `/corpus` route shows the table + `/corpus/export` streams the download.
  - [x] **Done criteria:** the JSONL line count equals the table row count exactly (`modules/measure/test_corpus_exporter.py`).

- [x] **slice-17-risk-report** (M). DONE — PDF deferred.
  - [x] `modules/measure/risk_report.py`: SR 11-7 sections rendered from real run state; every numeric field carries its Postgres source-row reference inline (`[table:id]`).
  - [ ] PDF generation DEFERRED: a clean pure-Python md→pdf path needs a heavy new dependency; the dashboard renders the Markdown and PDF export is a tracked follow-up (see `orchestrator/api.py` `/reports/{run_id}` docstring).
  - [x] **Done criteria (Markdown):** the report renders for a real run with source-row references (`modules/measure/test_risk_report.py`).

- [x] **slice-18-halt-cert** (M). DONE.
  - [x] `modules/measure/halt_rule.py`: a persisted halt-state singleton flips `halted=true` when white-box recall falls below the threshold (default 0.7).
  - [x] The orchestrator refuses new launches with HTTP 409 and a typed error body (recall + threshold).
  - [x] Dashboard banner reads `/halt` on every route.
  - [x] **Done criteria:** dropping recall trips the banner + the 409 (`modules/measure/test_halt_rule.py`).

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
