# Tasks

Slice-grained checklist. Each slice ends with a running platform, a passing `vouch` report, and a single squash-merged commit on `main`. Tasks are checked off in the same commit that lands the code (the diff makes the slice auditable).

Convention: `pillar/slice-N-short-title`. Slices 0 to 4 are critical-path-sequential. Slices 5 onward fan out per `plan.md` section 8. Owners are abbreviated **T** (Targets-and-Oracles), **R** (Red), **B** (Blue), **M** (Measure), **A** (all four).

## Current slice

- [x] **slice-0-foundation** (A). Foundational artifacts (this file plus four others), repo scaffolding, Continuous Integration (CI) skeleton.

## Next slice

- [ ] **slice-1-target-protocol** (T). `interfaces.Target` Protocol, `DummyTarget`, end-to-end smoke through the orchestrator loop.

## Backlog

### Critical path (sequential)

- [x] **slice-0-foundation** (A).
  - [x] `constitution.md`, `spec.md`, `plan.md`, `tasks.md`, `QA_ADVERSARY.md` at repo root, populated (no template placeholders, grep clean).
  - [x] `CONTRIBUTING.md` with squash-per-slice and shared-folder discipline.
  - [x] `design/claude-design-brief.md` ready for paste into claude.ai/design.
  - [x] `pyproject.toml` with `python = ">=3.12"`, FastAPI, SQLAlchemy, Alembic, Anthropic SDK, Hypothesis, LightGBM, scikit-learn, structlog. `ruff` and `mypy --strict` configured. (DEVIATION: Modal replaced by a local Docker sandbox — see bead cr-dev; LLM via OpenRouter-routed Anthropic models.)
  - [x] `orchestrator/interfaces/{target,oracle,red,blue,measure}.py` stub Protocols. No implementations yet.
  - [x] `shared/types/`: `Attack`, `Verdict`, `AuditTrace`, `TargetSpec`, `OracleVote`, `RunId`, `AttackBudget`, `SealedSpec` as `@dataclass(frozen=True, slots=True)`.
  - [x] `shared/persistence/`: async SQLAlchemy engine, base session, Alembic `env.py`. Migrations for `runs`, `verdicts`, `attacks`, `llm_calls`, `sandbox_jobs`, `health_probes`. (Plus `specs`.)
  - [x] FastAPI `POST /runs`, `GET /health`, `GET /runs/:runId/stream` (SSE).
  - [x] Pre-merge check script `scripts/check_module_imports.py` that rejects `from modules.<x>` inside `modules/<y>/` and rejects pull requests touching `modules/` and `shared/types/` together.
  - [x] GitHub Actions workflow `.github/workflows/ci.yml` runs ruff, mypy strict, pytest, the pre-merge check script.
  - [ ] Dual-push confirmed. (DEVIATION: GitLab remote not configured on this clone — GitHub-only push; tracked in bead cr-dev.)
  - [x] **Done criteria for `vouch`:** `pytest tests/integration/test_smoke.py::test_post_runs_returns_run_id` passes; `ruff check .` clean; `mypy --strict .` clean.

- [x] **slice-1-target-protocol** (T).
  - [x] `interfaces.Target` Protocol with `submit(input)` (consolidated `query_target` into `submit`) plus `health()`.
  - [x] `modules/targets/dummy/` concrete `DummyTarget` returning canned `(output, score)`.
  - [x] `orchestrator/wiring.py` registers `DummyTarget` (and a `StaticRedAgent`) so the loop runs a real round.
  - [x] Integration test exercises one loop round end to end with `DummyTarget`.
  - [x] **Done criteria for `vouch`:** `tests/integration/test_loop_smoke.py::test_one_round_with_dummy` passes.

- [x] **slice-2-fraud-target** (T).
  - [x] `modules/targets/fraud/`: dataset downloader (`scripts/fetch_fraud_dataset.py`, OpenML mirror — DEVIATION from Kaggle, no creds), LightGBM trainer (`train.py`), serialized model under `artifacts/fraud-v1.lgb`, `FraudTarget` Protocol implementation. Plus `data.py` with the sealed 3-way split (train / holdout / eval).
  - [x] Self-test endpoint `/health/targets/fraud` returns model file checksum (`model_sha256`) and last training timestamp.
  - [x] Integration test with real data: `pytest tests/integration/test_fraud_target.py`.
  - [x] **Done criteria for `vouch`:** model trained on real data (not a stub, n_train≈199k), AUC on held-out eval = 0.916 (≥ 0.85), health endpoint returns 200 green.

- [ ] **slice-3-code-agent-target** (T).
  - [ ] `modules/targets/code_agent/`: producer that takes a sealed `code_spec.yaml` and returns Python source via Claude Sonnet 4.6 tool use.
  - [ ] Producer runs inside the Modal sandbox (per slice 4 wiring).
  - [ ] Self-test endpoint `/health/targets/code_agent` runs a "produce hello world" round trip in under one second.
  - [ ] **Done criteria for `vouch`:** integration test produces real Python code that compiles via `ast.parse`.

- [x] **slice-4-sealed-spec-and-sandbox** (T).
  - [x] `shared/sandbox/`: local Docker job wrapper (DEVIATION from Modal — bead cr-dev). Strips env vars, denies ALL network egress (`--network none`); returns stdout/stderr/exit/job_ref.
  - [x] `shared/types/sealed_spec.py`: typed `SealedSpec` value object (landed slice 0; + dict round-trip).
  - [x] Spec sealing: spec stored in Postgres `specs` table, read by oracles through a server-side resolver (`shared/persistence/resolver.py`). Producer container has no Postgres credentials and no network.
  - [x] "Seal Probe" fixture under `shared/sandbox/probes/` that, from inside the sandbox, tries to reach Postgres and the internet (Modal control plane N/A). All time out.
  - [x] Integration test runs the seal probe and asserts all probes failed.
  - [x] **Done criteria for `vouch`:** `tests/integration/test_sandbox_seal.py` passes; the producer (sandbox) cannot reach Postgres (seal probe `postgres.reachable=False`), while the server-side resolver can.

### Per-pillar (parallel after slice 4)

- [x] **slice-5-held-out-oracle** (T). (fraud branch; Opus-generated tests are the code-agent branch, slice 3.)
  - [x] `modules/oracles/held_out/`: for fraud the held-out tests are the sealed data partition (real labels the producer never trained on — DEVIATION from Opus-generated, more honest, bead cr-dev). Ground truth rides in `attack.metadata` (the producer is handed only `payload`); fires on a mislabelled known fraud, with reason.
  - [x] `HoldoutFraudRed` draws real held-out frauds through the loop; the producer cannot read the labels (metadata channel + sandbox seal).
  - [x] Self-test endpoint (`oracles/fraud/held_out`).
  - [x] **Done criteria for `vouch`:** ground-truth logic verified; through the loop the held-out oracle surfaces every real producer miss (9/9 over 60 draws); producer never sees `true_label`.

- [x] **slice-6-metamorphic-oracle** (T).
  - [x] `modules/oracles/metamorphic/`: three metamorphic relations (uniform jitter, Amount scaling, global scaling — each must preserve the label) checked at runtime, pass/fail reported per rule. Rules are hardcoded mock-first; the Sonnet synthesis hook is the production path (bead cr-dev). Deterministic (seed from attack), so it replays.
  - [x] **Done criteria for `vouch`:** 3 rules per spec, fires on an unstable producer, silent on a stable one, surfaced in the vote observation.

- [x] **slice-7-differential-oracle** (T). (fraud branch; code Sonnet-vs-Haiku lands with slice 3.)
  - [x] `modules/oracles/differential/`: for fraud, LightGBM versus IsolationForest (held-out AUC ~0.94; score thresholded at the 98th training percentile, not the too-strict `predict()`).
  - [x] Both implementations score per submission; the oracle fires only on disagreement in the missed-fraud direction (one vote of four — never trusts a single side).
  - [x] **Done criteria for `vouch`:** fire logic verified deterministically (anomalous+missed→fires, agreement→silent); false-positive rate on legit < 5%. (Dataset loader moved to `shared/datasets/` to keep the module-import rule.)

- [x] **slice-8-property-fuzz-oracle** (T).
  - [x] `modules/oracles/property_fuzz/`: genuine `hypothesis` search (derandomized for replay) over the producer's output invariants — fraud_probability in [0,1], label in {0,1}, determinism.
  - [x] **Done criteria for `vouch`:** finds a violation on a deliberately broken producer (out-of-range probability and non-deterministic), stays silent on the sound LightGBM.

- [x] **slice-9-llm-judge-oracle** (T).
  - [x] `modules/oracles/llm_judge/`: Opus 4.8 reads output + obligation and votes pass/fail with reason (mock-first via ScriptedLLM; real Opus on `CRUCIBLE_REAL_JUDGE=1`, validated live $0.0025/call). Robust JSON + keyword parsing.
  - [x] Judge gets 0.5 vote weight; `test_judge_half_vote_cannot_decide_alone` proves a lone judge fire stays clean (0.5 < 2.0).
  - [ ] Verdict view marks the judge card "one vote" — frontend (PR #1 wiring).

- [x] **slice-10-verdict-aggregator** (T).
  - [x] `modules/oracles/aggregator.py`: vote tally per `plan.md` section 3 (4×1.0 + judge 0.5, threshold 2.0; injected into the loop via the `VerifyFn` port so loop.py imports no concrete module).
  - [x] Audit trace JSON written to `verdicts.audit_trace` (summary + every oracle's verbatim reason). Loop persists a verdict per round + emits an SSE `verdict` event.
  - [x] Replay determinism: seed captured on the verdict; deterministic oracles replay identically.
  - [x] **Done criteria for `vouch`:** `test_verdict_replays_byte_equal` re-runs the verdict and asserts byte-equal votes/tally/outcome; aggregator threshold logic verified (judge alone cannot decide).

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
  - [ ] `AI_INTERVIEW_PREP.md` populated against `spec.md` rubric mapping.
  - [ ] Architecture website `website/index.html` updated for the as-built numbers.
  - [ ] Render deployment verified end to end per the global CLAUDE.md "DEPLOY-VERIFY-OR-DIE" checklist.

### Stretch (only after slice 19 lands clean)

- [ ] **stretch-co-evolution-curve**. Plot ASR versus detection over N rounds at `/co-evolution`.
- [ ] **stretch-time-series-target**. Add autoencoder, GMM, or DAGMM for time-series anomaly detection.
- [ ] **stretch-research-agent-target**. Promote the stub to a real implementation.
- [ ] **stretch-verifier-tournament**. Cheapest-verifier router, hierarchical decomposition, debate escalation, live human-review-budget meter.
- [ ] **stretch-submission-portal**. Producer login, billing layer, producer-scoped permissions.
