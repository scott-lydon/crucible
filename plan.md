# Plan

How Crucible gets built. Architecture, component breakdown, data flow, sequencing. Every decision in this file traces back to a `spec.md` user story and a `constitution.md` rule.

This is the canonical engineering plan. The architecture website at `website/index.html` renders the same content polished; the dashboard at `dashboard/` renders the live numbers. If those drift from this file, they are wrong and this file is right.

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

The polished version of this lives at `website/index.html` with logos and decision tables, per the project CLAUDE.md "Architecture website per assignment" rule. Update both in the same commit.

## 2. Module boundaries (hexagonal layout)

Per `constitution.md` section 2.

```
crucible/
  shared/
    types/               # Attack, Verdict, AuditTrace, TargetSpec, RunId, etc.
    persistence/         # SQLAlchemy async session, Alembic migrations
    telemetry/           # structlog, OpenTelemetry traces, cost meter
    sandbox/             # sandbox adapter port + local Docker adapter (Modal optional)
  orchestrator/
    interfaces/          # Protocol definitions per pillar (Target, Oracle,
                         #   RedAgent, BlueAgent, MeasureSink)
    loop.py              # red → verify → harden → measure, one round = one
                         #   DB transaction
    api.py               # FastAPI: POST /runs, SSE /runs/:runId/stream,
                         #   GET /health
    wiring.py            # DI: which concrete class satisfies which interface
  modules/
    targets/             # Pillar 1: generic Target ADAPTERS only (no victims)
      local_model/       # load + query a serialized model artifact
      model_endpoint/    # query a remote model over HTTP
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
  examples/
    targets/             # demo VICTIMS — the systems Crucible evaluates; NOT
      fraud_synth/       #   part of the harness; reached via an adapter through
                         #   the Target Protocol; externalizable to a separate
                         #   repo. fraud_synth = synthetic flawed detector +
                         #   generator. Later: fraud_kaggle/, code_agent/.
  tests/
    integration/         # orchestrator-owned, exercise the whole loop
  design/
    claude-design-brief.md   # input for claude.ai/design exports
```

The harness must not import from `examples/` (enforced by the pre-merge import check); only `orchestrator/wiring.py` (the composition root) wires a concrete victim.

Each module ships its own `tests/` directory and its own `README.md` documenting the module's interface contract.

## 3. Per-pillar component responsibilities

### Pillar 1, Targets and Oracles

**Targets module** (`modules/targets/`). Implements `interfaces.Target` Protocol. Ships generic adapters only; the concrete victims they reach live in `examples/targets/` (see section 2) and are wired at the composition root.

| Subcomponent | Inputs | Outputs | Persistence | Self-test |
|---|---|---|---|---|
| fraud adapter (loads a serialized model via `local_model`) + victim model in `examples/targets/`; trained artifact + dataset external | Transaction record (JSON) | Fraud probability (float) | Trained model artifact under `examples/targets/.../fraud-vN.lgb` (N is the version integer) | `/health/targets/fraud` returns model file checksum + last training timestamp |
| `code_agent/` (adapter; victim producer in `examples/targets/`) | Function specification (sealed YAML) | Python source string | Producer stdout streamed to Postgres `producer_runs` | `/health/targets/code_agent` returns a one-second "produce hello world" round trip |
| `research_agent/` (stub adapter) | (stubbed) | (stubbed) | (none) | `/health/targets/research_agent` returns `{status: "stub"}` |

**Sandbox** (`shared/sandbox/`). Sandbox adapter (local Docker v1; Modal optional). Strips environment, denies network egress, returns `{stdout, stderr, exit_code, job_id}`. The "Seal Probe" feature called out in US-9 is implemented as a fixture under `shared/sandbox/probes/`.

**Sealed spec** (`shared/types/sealed_spec.py`). YAML loaded into a typed `SealedSpec` value object containing `obligations[]`, `invariants[]`, `holdout_generator_kind`. Stored in Postgres `specs` table, read by oracles through a server-side resolver that the producer container cannot reach.

**Oracles module** (`modules/oracles/`). Implements `interfaces.Oracle`. Five concrete classes.

| Subcomponent | What it checks | LLM use | Persistence |
|---|---|---|---|
| `held_out/` | Fresh tests generated by Claude Opus 4.8 after submission, run against producer output | Opus 4.8 (generation) | `held_out_tests` table; tests deleted after run |
| `metamorphic/` | If input changes this way, output must change that way; rules derived from spec invariants | Sonnet 4.6 (rule synth) | `metamorphic_rules` table |
| `differential/` | Spawn a second implementation from a different model family, require agreement | Sonnet 4.6 (code), or sklearn IsolationForest (fraud) | `differential_runs` table |
| `property_fuzz/` | `hypothesis` fuzzing over spec invariants | None | `fuzz_findings` table |
| `llm_judge/` | Opus 4.8 reads the output and votes pass / fail with reason | Opus 4.8 | `judge_votes` table |

**Verdict aggregator** (`modules/oracles/aggregator.py`). Vote-weighted: four oracles each get 1 vote, judge gets 0.5. Threshold 2.0 for pass. Persists `verdicts` row with full audit trace JSON.

### Pillar 2, Red

**Red module** (`modules/red/`). Implements `interfaces.RedAgent`.

| Subcomponent | Responsibility | LLM | Persistence |
|---|---|---|---|
| `search.py` | Reason about why caught, propose minimal change, iterate up to budget | Sonnet 4.6 inner loop | `attacks` table |
| `catalog.py` | Persist successful tactics, surface for reuse, distill across runs | None at write; Sonnet 4.6 to summarize on read | `strategy_catalog` table + JSONL append-only log |
| `white_box.py` | Same `search.py` but with verifier scheme injected into the prompt | Opus 4.8 (more reasoning headroom for harder problem) | `attacks` table with `white_box=true` |
| `hybrid.py` | When constraint satisfaction fails, LLM proposes the strategy, a constrained numeric search executes it | Sonnet 4.6 (strategy) + `scipy.optimize` (executor) | `attacks` table with `hybrid=true` |

### Pillar 3, Blue

**Blue module** (`modules/blue/`). Implements `interfaces.BlueAgent`.

| Subcomponent | Responsibility | LLM | Persistence |
|---|---|---|---|
| `proposer.py` | Read catalog, propose features / samples / ensemble | Sonnet 4.6 | `blue_patches` table |
| `retrainer.py` | Apply the patch, run training, produce a new model artifact | None | `artifacts/fraud-vN.lgb` (next integer), `model_versions` table |
| `holdout_validator.py` | Re-evaluate detection on a held-out attack set defined up front (never the patch's training attacks) | None | `holdout_runs` table |

### Pillar 4, Measure

**Measure module** (`modules/measure/`). Implements `interfaces.MeasureSink` and `interfaces.HealthRegistry`.

| Subcomponent | Responsibility | Frontend route |
|---|---|---|
| `sse_backend.py` | Stream every persisted row insert as an SSE event to the dashboard | `/runs/:runId` |
| `metrics_aggregator.py` | Compute the five headline tiles from `verdicts` and `attacks` tables | `/metrics` |
| `corpus_exporter.py` | Stream `attacks` rows where `succeeded=true` as JSONL | `/corpus` |
| `risk_report.py` | Render SR 11-7 Markdown from a run's persisted state | `/reports/:runId` |
| `halt_rule.py` | Polls `metrics.recall_white_box`; if below threshold, sets a Postgres `halted=true` flag the orchestrator checks on new runs | All routes (banner) |
| `health.py` | Aggregates every module's `/health/<pillar>/<subcomponent>` probe | `/health` |

**Dashboard** (`dashboard/`). React SPA. Routes per the previous-turn list. Each route is a thin client over the FastAPI endpoints above.

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

One transaction per `emit`. The dashboard never reads from the loop; it reads from Postgres via the SSE backend.

## 5. Decision table

| Decision | What we chose | Alternative considered | Why |
|---|---|---|---|
| Search engine | LLM semantic reasoning | Gradient-based attacks | Gradients produce illegal samples (negative amounts, impossible timestamps). README section 4. |
| Verification | Non-colluding ensemble of four oracles plus one judge | Single LLM judge | Single judge shares producer blind spots. |
| Held-out tests | Generated post-submit, never exposed | Static held-out set | Static sets leak; static beats inattentive attackers, not capable ones. |
| Differential oracle | Second implementation from a different model family | Same family, different seed | Same family shares blind spots. |
| Target coupling | Thin adapter, one shared core | Core per target | Target-agnostic is the README's first promise. |
| Catch-rate claim | White-box self-test on every pass | Black-box only | Black-box catch rate is recall against ignorance. |
| Constraint satisfaction failure | Hybrid: LLM proposes, numeric search executes | Pure LLM search | Graceful degradation when valid samples are scarce. |
| Patch validation | Held-out attack set defined up front | Validate on patch's training attacks | Prevents the blue loop from overfitting to known attacks. |
| Stop rule | Halt certification at residual red line | Ship regardless of residual | Capability-threshold gating, per Responsible Scaling Policy spirit. |
| Persistence | Postgres 16 | SQLite | Concurrent writes from pillars break SQLite. |
| Sandbox | **Local Docker/subprocess (v1); Modal optional adapter** | Modal, nsjail | Ports-and-adapters: Docker gives real isolation locally with zero external account; Modal swappable for managed production. |
| Dashboard SPA stack | React 18 + Vite + Tailwind + Recharts + Router | Next.js, Streamlit | Existing architecture site palette and the team's React familiarity. |
| Producer sandbox to oracle communication | Output written to a write-only Postgres row by the orchestrator after the sandbox returns; oracles read from Postgres | Direct pipe sandbox → oracles | Direct pipe would require the sandbox to know oracle endpoints. |

## 6. Trade-offs (honest residuals)

- **Per-loop LLM cost and latency.** Accept: cache prompts, batch where shape allows, use Sonnet 4.6 on the inner loop. Bites at many co-evolution rounds; mitigation is the budget control on `POST /runs`.
- **The spec is a proxy for intent.** Accept: report verifier recall continuously and halt at the red line. Bites when unknown hack classes exist.
- **Oracles may share blind spots.** Accept: four mechanisms fail differently, white-box adversary rewarded for finding shared gaps. Bites if all four correlate on an unanticipated class.
- **Blue overfits or does not converge.** Accept: held-out attack set defined up front, validation on that set. Bites if the held-out set is not representative.
- **Self-deceiving evaluation.** Accept: freeze the evaluation protocol on day one. Bites if the frozen protocol itself carries a flaw.
- **Constraint satisfaction fails.** Accept: hybrid (LLM proposes, constrained search executes). Bites in domains where no valid sample exists.
- **Dashboard cost.** Every SSE-pushed event is also a Postgres write. Mitigation: batch verdict-aggregator writes per round, never per oracle vote.

## 7. Transparency cross-cuts (per `constitution.md` section 4)

Every persisted Postgres row carries:

- `created_at` (timestamptz)
- `pillar` (enum: targets, oracles, red, blue, measure, orchestrator)
- `dollars_spent` (numeric, zero if no LLM call)
- `seed` (text, capture for replay determinism)
- `audit_trace` (JSONB, full reasoning surface)
- `parent_action_id` (foreign key for replay chains)

Every LLM call is logged to `llm_calls` (prompt, raw response, parsed output, model, tokens, dollars, captured seed, parent action id). The dashboard's Inspect button on any trace line opens this row.

Every sandbox job is logged to `sandbox_jobs` (job id, env applied, network rules, exit code, stdout, stderr, captured seed). Dashboard surfaces the live stream and the post-run record.

Every subcomponent registers itself with the orchestrator at startup via `MeasureSink.register_health_probe(name, probe_fn)`. The `/health` route walks the registry on every request.

## 8. Sequencing

Slices land in the order in `tasks.md`. Slice 0 to 4 are the critical path; everything from slice 5 fans out across pillars.

The critical-path property: slice 0 to 4 must land before any other slice. Inside slice 5 to 18, the per-pillar dependency graph is:

```
Pillar 1 (Targets+Oracles): 5 → 6 → 7 → 8 → 9 → 10
Pillar 2 (Red):             11 → 12, 13
Pillar 3 (Blue):            14
Pillar 4 (Measure):         15 → {16, 17, 18}
```

After slice 4 lands, the four pillar owners run their dependency chains in parallel against the same Postgres and the same orchestrator. Slice 19 (demo polish) is a team-wide convergence at the end.

## 9. Deployment

- **Production:** Render. One web service (the FastAPI app + dashboard build) plus one Postgres service. The sandbox runs per-invocation (local Docker today); a Modal adapter, if used, is per-invocation too.
- **Static dashboard hosting:** the dashboard's Vite build output is served from the same Render web service under `/app`, the architecture website under `/architecture`. Both behind the same origin.
- **Cache-busting:** Vite content-hashes filenames by default. `index.html` is served with `Cache-Control: no-cache` plus a `?v=<git-sha>` query string on the entry script, per the global CLAUDE.md "Static-asset cache poisoning" prevention rule.
- **Secrets:** Anthropic key, sandbox/provider credentials (if a managed sandbox adapter is used), Postgres URL stored as Render environment variables, never in the repo. Local development reads from `.env` which is `.gitignored`.

## 10. Operational

- Logs: structlog JSON to stdout, captured by Render. Each log line carries `run_id`, `pillar`, `subcomponent`, `seed`.
- Metrics: Postgres-backed; no Prometheus or Grafana in the two-week build.
- Traces: OpenTelemetry instrumentation on every interface boundary, exported to the dashboard's trace view, not to a third-party tracer.
- Cost: each LLM call writes its dollar cost to `llm_calls.dollars`; the cost meter in the dashboard reads aggregations from Postgres.
