# Architecture

How Crucible gets built. Topology, component breakdown, data flow, decisions,
trade-offs, the core bet, sequencing. Every decision here traces back to an
`acceptance-tests.md` user story and a `coding-practices.md` rule.

This is the canonical engineering source. The architecture website at
`website/index.html` renders the same content polished; the dashboard at `dashboard/`
renders the live numbers. If those drift from this file, they are wrong and this file is
right.

## 1. High-level topology

```
                              ┌───────────────────────────────────┐
                              │      Orchestrator (FastAPI)       │
                              │  loop.py  api.py  wiring.py       │
                              │  interfaces/{target,oracle,red,   │
                              │   blue,measure}.py                │
                              └────┬────┬────┬────┬────┬──────────┘
                                   │    │    │    │    │
                       ┌───────────┘    │    │    │    └─────────────┐
                       v                v    v    v                  v
                ┌──────────────┐  ┌──────────┐  ┌────────┐  ┌──────────────┐
                │ modules/     │  │ modules/ │  │modules/│  │ modules/     │
                │ targets/     │  │ oracles/ │  │ red/   │  │ blue/        │
                │ (adapters,   │  │ (4 +     │  │ (LLM   │  │ (auto-       │
                │  sandbox,    │  │  judge,  │  │  search│  │  hardening,  │
                │  spec seal)  │  │  verdict │  │  cat,  │  │  retrain,    │
                │              │  │  agg)    │  │  WB,   │  │  hold-out    │
                │              │  │          │  │  hybrid│  │  validate)   │
                └──────┬───────┘  └────┬─────┘  └────┬───┘  └──────┬───────┘
                       │               │             │              │
                       └───────┬───────┴─────────────┴──────────────┘
                               v
                        ┌──────────────┐         ┌────────────────────┐
                        │  shared/     │         │  modules/measure/  │
                        │  types       │         │  (SSE backend,     │
                        │  persistence │         │   exports, halt    │
                        │  telemetry   │         │   rule, dashboard) │
                        │  sandbox     │         └─────────┬──────────┘
                        └──────┬───────┘                   │
                               v                           v
                       ┌───────────────┐           ┌──────────────┐
                       │  Postgres 16  │           │  dashboard/  │
                       │  (Supabase)   │           │  React SPA   │
                       └───────────────┘           └──────────────┘
```

The polished version of this lives at `website/index.html` with logos and decision
tables. Update both in the same commit.

## 2. Module boundaries (hexagonal layout)

Per `coding-practices.md` section 2.

```
crucible/
  shared/
    types/               # Attack, Verdict, AuditTrace, TargetSpec, RunId, etc.
    persistence/         # SQLAlchemy async session, Alembic migrations
    telemetry/           # structlog, OpenTelemetry traces, cost meter
    sandbox/             # Modal job wrapper (infrastructure)
  orchestrator/
    interfaces/          # Protocol definitions per pillar (Target, Oracle,
                         #   RedAgent, BlueAgent, MeasureSink)
    loop.py              # red → verify → harden → measure, one round = one
                         #   DB transaction
    api.py               # FastAPI: POST /runs, SSE /runs/:runId/stream,
                         #   GET /health
    wiring.py            # DI: which concrete class satisfies which interface
  modules/
    targets/             # Pillar 1: adapters, sealed spec, sandbox client
      fraud/             # LightGBM on Kaggle creditcard
      code_agent/        # Claude Sonnet 4.6 producer
      research_agent/    # Stub, wiring.py skips at runtime
    oracles/             # Pillar 1 cont: held-out, metamorphic, differential,
                         #   property fuzz, LLM judge, verdict aggregator
    red/                 # Pillar 2: search, catalog, white-box, hybrid
    blue/                # Pillar 3: patch proposer, retrainer, held-out
                         #   validator
    measure/             # Pillar 4: SSE backend, exports, halt rule,
                         #   dashboard backend
  dashboard/             # React + Vite SPA (Measure pillar's frontend)
  website/               # Architecture website (existing, public-facing)
    index.html
  tests/
    integration/         # orchestrator-owned, exercise the whole loop
  design/
    claude-design-brief.md   # input for claude.ai/design exports
```

Each module ships its own `tests/` directory and its own `README.md` documenting the
module's interface contract.

## 3. Per-pillar component responsibilities

Each table lists name, inputs, outputs, persistence, and self-test. The per-pillar
failure modes follow each table; a failure surfaces as a typed error, never a swallowed
exception (`coding-practices.md` section 6).

### Pillar 1, Targets and Oracles

**Targets module** (`modules/targets/`). Implements `interfaces.Target` Protocol. Three
sub-adapters.

| Subcomponent | Inputs | Outputs | Persistence | Self-test |
|---|---|---|---|---|
| `fraud/` | Transaction record (JSON) | Fraud probability (float) | Trained model in `artifacts/fraud-vN.lgb` (N is the version integer) | `/health/targets/fraud` returns model file checksum + last training timestamp |
| `code_agent/` | Function specification (sealed YAML) | Python source string | Producer stdout streamed to Postgres `producer_runs` | `/health/targets/code_agent` returns a one-second "produce hello world" round trip |
| `research_agent/` | (stubbed) | (stubbed) | (none) | `/health/targets/research_agent` returns `{status: "stub"}` |

**Sandbox** (`shared/sandbox/`). Modal job wrapper. Strips environment, denies network
egress, returns `{stdout, stderr, exit_code, modal_job_id}`. The "Seal Probe" feature
called out in US-9 is implemented as a fixture under `shared/sandbox/probes/`.

**Sealed spec** (`shared/types/sealed_spec.py`). YAML loaded into a typed `SealedSpec`
value object containing `obligations[]`, `invariants[]`, `holdout_generator_kind`.
Stored in Postgres `specs` table, read by oracles through a server-side resolver that
the producer container cannot reach.

**Oracles module** (`modules/oracles/`). Implements `interfaces.Oracle`. Five concrete
classes.

| Subcomponent | What it checks | LLM use | Persistence |
|---|---|---|---|
| `held_out/` | Fresh tests generated by Claude Opus 4.8 after submission, run against producer output | Opus 4.8 (generation) | `held_out_tests` table; tests deleted after run |
| `metamorphic/` | If input changes this way, output must change that way; rules derived from spec invariants | Sonnet 4.6 (rule synth) | `metamorphic_rules` table |
| `differential/` | Spawn a second implementation from a different model family, require agreement | Sonnet 4.6 (code), or sklearn IsolationForest (fraud) | `differential_runs` table |
| `property_fuzz/` | Random-sampling property fuzzing over spec invariants, run in the sealed sandbox. The sandbox denies all network, so the `hypothesis` library cannot be installed there; stdlib random sampling finds violations all the same. Hypothesis-in-sandbox is deferred. | Sonnet 4.6 (writes the fuzz function) | `fuzz_findings` table |
| `llm_judge/` | Opus 4.8 reads the output and votes pass / fail with reason | Opus 4.8 | `judge_votes` table |

**Verdict aggregator** (`modules/oracles/aggregator.py`). Vote-weighted: four oracles
each get 1 vote, judge gets 0.5. Threshold 2.0 for pass. Persists `verdicts` row with
full audit trace JSON.

**Failure modes.** Dataset download fails: typed `DatasetUnavailable` error, no
fallback to a sample file. Model fails to train: `TargetTrainingFailed` naming the
`LGBMClassifier.fit` traceback. Sandbox cannot launch: `SandboxLaunchFailed` pointing
at the Modal token and the egress rule. An oracle's LLM call times out: the verdict
records that oracle's vote as `unavailable` with the error, and the aggregator reports
on the remaining votes rather than guessing.

### Pillar 2, Red

**Red module** (`modules/red/`). Implements `interfaces.RedAgent`.

| Subcomponent | Responsibility | LLM | Persistence |
|---|---|---|---|
| `search.py` | Reason about why caught, propose minimal change, iterate up to budget | Sonnet 4.6 inner loop | `attacks` table |
| `catalog.py` | Persist successful tactics, surface for reuse, distill across runs | None at write; Sonnet 4.6 to summarize on read | `strategy_catalog` table + JSONL append-only log |
| `white_box.py` | Same `search.py` but with verifier scheme injected into the prompt | Opus 4.8 (more reasoning headroom for harder problem) | `attacks` table with `white_box=true` |
| `hybrid.py` | When constraint satisfaction fails, LLM proposes the strategy, a constrained numeric search executes it | Sonnet 4.6 (strategy) + `scipy.optimize` (executor) | `attacks` table with `hybrid=true` |

**Failure modes.** Budget exhausted before an evasion lands: a clean "no evasion within
budget" result, recorded, not an error. LLM produces an invalid sample three rounds
running: the hybrid fallback fires automatically (`hybrid.py`). Catalog read finds no
prior tactic: the search starts cold, which is expected, not a failure.

### Pillar 3, Blue

**Blue module** (`modules/blue/`). Implements `interfaces.BlueAgent`.

| Subcomponent | Responsibility | LLM | Persistence |
|---|---|---|---|
| `proposer.py` | Read catalog, propose features / samples / ensemble | Sonnet 4.6 | `blue_patches` table |
| `retrainer.py` | Apply the patch. For the fraud target: run a LightGBM training pass and emit a new `.lgb` artifact. For the code-agent target: apply the prompt-and-configuration diff and emit a new agent-config row. The vendor language model the code agent talks to is never modified. | None | `artifacts/fraud-vN.lgb` (next integer) for fraud, `agent_configs` row (next version) for code-agent; `model_versions` table records both under one schema |
| `holdout_validator.py` | Re-evaluate detection on a held-out attack set defined up front (never the patch's training attacks) | None | `holdout_runs` table |

**Trigger route.** `POST /runs/{run_id}/blue` (added 2026-06-24, US-7) is the
operator-facing entry that drives the blue loop for a completed run: it reads the
run's undetected attacks (falls back to all attacks when the ensemble caught
everything), calls `BlueProposer.propose_patch`, persists the patch via
`BlueStore`, and returns `{patch_id, kind}`. The blue-patch review view
(`slice-03-blue-patch-review`, `GET /blue/{patch_id}`) renders the result.
Before this route existed there was no API path to create a patch, so the review
view could only ever show an empty state. Held-out before/after detection is
recorded only when a non-overlapping held-out attack set exists for the run;
otherwise the review honestly shows "no held-out validation recorded" rather than
a fabricated delta.

**Failure modes.** The held-out attack set overlaps the patch's training attacks: the
orchestrator refuses to apply the patch and returns a typed `HoldoutContamination`
error (US-7). Retrain crashes: `RetrainFailed` naming the artifact version it was
writing. The patch does not recover detection: a real, recorded "did not generalize"
result, surfaced honestly, never papered over.

### Pillar 4, Measure

**Measure module** (`modules/measure/`). Implements `interfaces.MeasureSink` and
`interfaces.HealthRegistry`.

| Subcomponent | Responsibility | Frontend route |
|---|---|---|
| `sse_backend.py` | Stream every persisted row insert as an SSE event to the dashboard | `/runs/:runId` |
| `metrics_aggregator.py` | Compute the five headline tiles from `verdicts` and `attacks` tables | `/metrics` |
| `corpus_exporter.py` | Stream `attacks` rows where `succeeded=true` as JSONL | `/corpus` |
| `risk_report.py` | Render SR 11-7 Markdown from a run's persisted state | `/reports/:runId` |
| `halt_rule.py` | Polls `metrics.recall_white_box`; if below threshold, sets a Postgres `halted=true` flag the orchestrator checks on new runs | All routes (banner) |
| `health.py` | Aggregates every module's `/health/<pillar>/<subcomponent>` probe | `/health` |

**Dashboard** (`dashboard/`). React SPA. Routes per `acceptance-tests.md` section 1.
Each route is a thin client over the FastAPI endpoints above.

**Failure modes.** A metric tile has zero contributing runs: renders the literal text
"Not yet measured" with a link to the Run Launcher, never a "0.0" sample value (US-10).
SSE transport drops: the live-connection indicator goes amber while reconnecting and red
when offline; halt and other controls disable rather than firing against a stale state.
The halt flag is set: the orchestrator returns HTTP 409 on new run launches with a typed
error body (US-13).

## 4. Data flow, one round end to end

```mermaid
sequenceDiagram
  autonumber
  participant Op as Operator (UI)
  participant API as FastAPI
  participant Loop as Loop
  participant TGT as Target.submit
  participant ORA as Oracle.verify
  participant CAT as Catalog
  participant BLUE as BlueAgent
  participant MEAS as MeasureSink

  Op->>API: POST /runs (sealed spec + budget)
  API->>Loop: start_run(run_id, spec, budget)
  loop until budget exhausted
    Loop->>TGT: submit(input)
    TGT-->>Loop: output + producer audit
    Loop->>ORA: verify(input, output, spec)
    ORA-->>Loop: verdict + audit
    Loop->>MEAS: emit(verdict)
    MEAS-->>Op: SSE event
    alt undetected_hack
      Loop->>CAT: distill(attack, verdict)
      CAT-->>Loop: ok
    end
  end
  Loop->>BLUE: propose_patch(catalog_slice)
  BLUE-->>Loop: patch + holdout_validation
  Loop->>MEAS: emit(patch_result)
  Loop->>TGT: white_box pass (scheme injected)
  Note over Loop,MEAS: white-box catch rate computed
  Loop->>MEAS: emit(run_complete)
  MEAS-->>Op: SSE event, run page transitions to "complete"
```

One transaction per `emit`. The dashboard never reads from the loop; it reads from
Postgres via the SSE backend.

## 5. Decision table

| Decision | What we chose | Alternative considered | Why | Rubric pillar |
|---|---|---|---|---|
| Search engine | LLM semantic reasoning | Gradient-based attacks | Gradients produce illegal samples (negative amounts, impossible timestamps). README section 4. | Architecture |
| Verification | Non-colluding ensemble of four oracles plus one judge | Single LLM judge | Single judge shares producer blind spots. | Testing |
| Held-out tests | Generated post-submit, never exposed | Static held-out set | Static sets leak; static beats inattentive attackers, not capable ones. | Security |
| Differential oracle | Second implementation from a different model family | Same family, different seed | Same family shares blind spots. | Testing |
| Target coupling | Thin adapter, one shared core | Core per target | Target-agnostic is the README's first promise. | Architecture |
| Catch-rate claim | White-box self-test on every pass | Black-box only | Black-box catch rate is recall against ignorance. | Security |
| Constraint satisfaction failure | Hybrid: LLM proposes, numeric search executes | Pure LLM search | Graceful degradation when valid samples are scarce. | Architecture |
| Patch validation | Held-out attack set defined up front | Validate on patch's training attacks | Prevents the blue loop from overfitting to known attacks. | Testing |
| Stop rule | Halt certification at residual red line | Ship regardless of residual | Capability-threshold gating, per Responsible Scaling Policy spirit. | Security |
| Persistence | Postgres 16 | SQLite | Concurrent writes from pillars break SQLite. | Scalability |
| LLM access | Local `claude` CLI on the Claude Max subscription | Metered Anthropic API key | The subscription is already paid, so local runs and the demo cost nothing per token; the CLI still reports per-call cost for the dashboard. A metered key is the server-deploy fallback. | Scalability |
| LLM model/timeout override | `CRUCIBLE_LLM_MODEL_OVERRIDE` (forces every call to one model, e.g. `claude-haiku-4-5-20251001` for a cheap/fast validation pass) and `CRUCIBLE_LLM_TIMEOUT_SECONDS` (raises the per-call CLI timeout, default 180s) | Hardcoded per-agent models only | A full real run drives ~7+ sequential `claude` CLI calls (red ×N, target, 4 oracles, judge); on sonnet/opus a single call could exceed the 180s default and fail the whole run. The env overrides let a run be validated on haiku first, then promoted to sonnet/opus. Defaults unchanged when unset. | Operability |
| Sandbox | Docker (`--network none`) first, Modal as the hosted target | nsjail | Docker is already on the dev machine and seals egress with no new account; Modal becomes the hosted path once a token is added. | Security |
| Dashboard SPA stack | React 18 + Vite + Tailwind + Recharts + Router | Next.js, Streamlit | Existing architecture site palette and the team's React familiarity. | Scalability |
| Producer sandbox to oracle communication | Output written to a write-only Postgres row by the orchestrator after the sandbox returns; oracles read from Postgres | Direct pipe sandbox to oracles | Direct pipe would require the sandbox to know oracle endpoints. | Security |

## 6. Trade-offs (residuals)

- **Per-loop LLM cost and latency.** Accept: cache prompts, batch where shape allows,
  use Sonnet 4.6 on the inner loop. Bites at many co-evolution rounds; mitigation is
  the budget control on `POST /runs`.
- **The spec is a proxy for intent.** Accept: report verifier recall continuously and
  halt at the red line. Bites when unknown hack classes exist.
- **Oracles may share blind spots.** Accept: four mechanisms fail differently,
  white-box adversary rewarded for finding shared gaps. Bites if all four correlate on
  an unanticipated class.
- **Blue overfits or does not converge.** Accept: held-out attack set defined up front,
  validation on that set. Bites if the held-out set is not representative.
- **Self-deceiving evaluation.** Accept: freeze the evaluation protocol on day one.
  Bites if the frozen protocol itself carries a flaw.
- **Constraint satisfaction fails.** Accept: hybrid (LLM proposes, constrained search
  executes). Bites in domains where no valid sample exists.
- **Dashboard cost.** Every SSE-pushed event is also a Postgres write. Mitigation:
  batch verdict-aggregator writes per round, never per oracle vote.

## 7. Transparency cross-cuts (per `coding-practices.md` section 3)

Every persisted Postgres row carries:

- `created_at` (timestamptz)
- `pillar` (enum: targets, oracles, red, blue, measure, orchestrator)
- `dollars_spent` (numeric, zero if no LLM call)
- `seed` (text, capture for replay determinism)
- `audit_trace` (JSONB, full reasoning surface)
- `parent_action_id` (foreign key for replay chains)

Every LLM call is logged to `llm_calls` (prompt, raw response, parsed output, model,
tokens, dollars, captured seed, parent action id). The dashboard's Inspect button on any
trace line opens this row.

Every Modal job is logged to `sandbox_jobs` (job id, env applied, network rules, exit
code, stdout, stderr, captured seed). Dashboard surfaces the live stream and the
post-run record.

Every subcomponent registers itself with the orchestrator at startup via
`MeasureSink.register_health_probe(name, probe_fn)`. The `/health` route walks the
registry on every request.

## 8. Sequencing

Slices land in the order in `tasks.md`. Slice 0 to 4 are the critical path; everything
from slice 5 fans out across pillars.

The critical-path property: slice 0 to 4 must land before any other slice. Inside slice
5 to 18, the per-pillar dependency graph is:

```
Pillar 1 (Targets+Oracles): 5 → 6 → 7 → 8 → 9 → 10
Pillar 2 (Red):             11 → 12, 13
Pillar 3 (Blue):            14
Pillar 4 (Measure):         15 → {16, 17, 18}
```

After slice 4 lands, the four pillar owners run their dependency chains in parallel
against the same Postgres and the same orchestrator. Slice 19 (demo polish) is a
team-wide convergence at the end.

## 9. Deployment

- **Production:** Render. One web service (the FastAPI app + dashboard build) plus one
  Postgres service. Modal is per-invocation, not deployed.
- **Static dashboard hosting:** the dashboard's Vite build output is served from the
  same Render web service under `/app`, the architecture website under `/architecture`.
  Both behind the same origin.
- **Cache-busting:** Vite content-hashes filenames by default. `index.html` is served
  with `Cache-Control: no-cache` plus a `?v=<git-sha>` query string on the entry script,
  so a new build cannot be served from a poisoned cache.
- **Secrets:** LLM access runs through the local `claude` CLI on the operator's Claude
  Max subscription, so local development and the live demo need no Anthropic key. A
  metered `ANTHROPIC_API_KEY` is a deploy-time fallback only, for a server with no
  Claude CLI session. The Postgres URL is required everywhere. The Modal token is
  required only once the sandbox moves from local Docker to hosted Modal. All real
  secrets live in Render environment variables or the `.gitignored` local `.env`,
  never in the repo.

## 10. Operational

- Logs: structlog JSON to stdout, captured by Render. Each log line carries `run_id`,
  `pillar`, `subcomponent`, `seed`.
- Metrics: Postgres-backed; no Prometheus or Grafana in the two-week build.
- Traces: OpenTelemetry instrumentation on every interface boundary, exported to the
  dashboard's trace view, not to a third-party tracer.
- Cost: each LLM call writes its dollar cost to `llm_calls.dollars`; the cost meter in
  the dashboard reads aggregations from Postgres.

## 11. The core bet

The single hardest piece, and the reason the project is worth attempting, is
**independent oracle generation that survives a white-box adversary.** If the oracles
only catch attacks against an attacker that does not know the verification scheme, the
catch rate is borrowed from the attacker's ignorance, not from the platform's design.
README sections 7 and 8 hold the full argument; the architectural commitments that fall
out of it are:

- **The white-box self-test runs every pass.** It is mandatory product behavior
  (US-14), not a stretch goal. The same red agent that did the black-box search becomes
  the auditor of the oracle ensemble it just attacked, with the verification scheme
  handed to it as input. What stays hidden is the instances (the specific held-out test
  cases, the per-run differential outputs), not the scheme.
- **The producer sandbox has no path to the verification artifacts.** Held-out test
  instances, the differential second implementation's outputs, and oracle internals are
  never readable from inside the producer container. Verified by an integration test
  that runs a Modal job and asserts the producer cannot resolve the Postgres host
  (`tests/integration/test_sandbox_seal.py`).
- **Held-out tests are generated after submission, never before.** A static held-out
  set leaks over time. The held-out oracle generates fresh tests post-submit from the
  sealed spec.
- **The catch-rate gap between black-box and white-box is the report card.** No second
  adversary is built and no third-party red team is contracted. A low white-box catch
  rate triggers the halt-certification rule until the oracles are strengthened or the
  spec is narrowed.

## 12. Out of scope (architecture)

These exclusions shape the topology, so they live here as well as in
`acceptance-tests.md` section 2.

- **Confidentiality and Availability.** Crucible targets the Integrity pillar of the
  classical information-security triad only. It is not a SQL-injection, secrets, or
  uptime tool. The README "What Crucible is not" section is binding.
- **The research-agent target adapter ships as a stub.** The adapter shape exists in
  `modules/targets/research_agent/`; `orchestrator/wiring.py` skips it at runtime in the
  two-week build.
- **Crucible certifies nothing.** It reports a catch rate against a white-box adversary
  and halts at a residual red line. The certification authority is whoever consumes the
  model risk report (the bank's model risk committee under SR 11-7 for the bank
  customer; the equivalent governance body for other segments).
- **Out of scope for the two-week build:** the submission portal, the automated
  specification compiler, and the full verifier tournament. Detail and reasons in
  `acceptance-tests.md` section 2.
