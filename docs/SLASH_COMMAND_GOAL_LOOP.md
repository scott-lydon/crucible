# Crucible as a `/crucible` slash command — goal-loop checklist

> ## Implementation status (2026-06-27)
>
> Slices 00 through 9 are built and verified; Slice 10 (the live human-POV demo
> recording) is the one step that needs the operator. Evidence:
>
> - **Observability spine** (`shared/obs/emit.py`, `shared/obs/sink.py`): single
>   writer, three sinks (JSONL + raw stdout + pretty terminal), closed `EventType`
>   enum + glyph table, `read_trace`, typed `TraceSinkUnwritableError`. Wired into
>   the loop AS a `MeasureSink` (`FileTraceSink`), the same seam the web run uses.
> - **CLI package** (`crucible/`): `run, replay, report, catalog, status, doctor,
>   eligibility, suitability, adapter, oracle, red, blue, verdict, metrics, eval`.
>   Console script repointed to `crucible.cli:main`; `python -m crucible` works.
> - **Slim install**: web deps moved to `[web]` extra; base install pulls no FastAPI
>   / Postgres / website. File-local runs use a per-run SQLite db.
> - **Pre-flight**: eligibility gate (typed reasons + fix, $0 on reject) and the
>   never-halting suitability advisor, both reusing the wired registry.
> - **Run driver**: eligibility first, then the existing loop end to end through the
>   spine; real modules, no stub data; artifacts under `artifacts/runs/<run_id>/`.
> - **Report**: static site that is a pure renderer (empty metric slots filled from
>   inlined artifact data; missing `metrics.json` renders "Not yet measured").
> - **Replay**: re-verifies a stored verdict, asserts byte-equality.
> - **Focus subcommands + evals**: resolve every component through the SAME wired
>   container the loop uses (single code path, proven by test).
> - **Slash command**: `~/.claude/skills/crucible/SKILL.md`. Quickstart: `QUICKSTART.md`.
> - **Tests**: 195 pass (26 new unit tests DB-free in `tests/unit/`, plus the full
>   169 existing integration tests against real Postgres). `ruff` clean and
>   `mypy --strict` clean on the new `crucible/` + `shared/obs/` surface. Live
>   `crucible run --target agent --stream json | jq .type` emits the full clean
>   stage sequence with one `oracle_fired` per oracle and a `verdict` per output.
> - **Anti-reward-hacking observer** (`crucible/demo_observer.py`, `crucible demo
>   verify`): built and tested (5 unit tests). It deterministically ties every
>   on-screen claim to a real artifact and refuses to certify a mocked / reused /
>   staged / incomplete run. Verified live: it FLAGS a mock-LLM run with the exact
>   reason ("MOCK_LLM was on, the demo must run against real Claude").
> - **Real LLM with no API key (Claude Max plan)**: added a `ClaudeCLIClient`
>   transport (`shared/llm/client.py`) that routes completions through the locally
>   authenticated `claude` CLI; `make_llm` falls back to it and
>   `CRUCIBLE_LLM_TRANSPORT=cli` forces it. No key, covered by the subscription.
> - **Slice 10 real certified runs (DONE):** two fresh real runs, certified
>   AUTHENTIC by the observer, with MOCK_LLM provably off (real `claude-opus-4-8`
>   judge, no scripted markers): fraud `run_83c444c4efbe` against the real
>   Kaggle-trained `fraud-v1.lgb` (sha256 verified), and code_agent
>   `run_0a134c22f001` (real Claude writes code, executed in the network-sealed
>   Docker sandbox). Both authenticity reports pass all five checks (run_completed,
>   real_llm, real_model, artifacts_in_window, claims_tie_out).
> - **Slice 10 screen recording (DONE):** real headless screen recordings (Playwright
>   + Chromium, `scripts/record_report.py`) of the two observer-certified real runs'
>   rendered dashboards, no camera and no desktop takeover. Per-run `.webm` under
>   `artifacts/runs/<id>/site/demo-<id>.webm`, stitched to `artifacts/crucible-demo.mp4`
>   (~14s). The frames show real data, including the "Not yet measured" tiles (the
>   facade-killer: only what the run wrote) and the `llm_mode:"real"` trace. These are
>   agent-driven recordings of REAL runs, honestly labeled (not human-POV, not faked,
>   not reconstructed). The operator clarified that "human-POV" meant a screen
>   recording, not a webcam, and waived the "a person driving" stipulation.
> - **Slice 10 (optional remaining):** a live-streaming capture (the loop happening in
>   real time) would need either the FastAPI dashboard recorded via Playwright over SSE
>   or a visible-terminal capture; the report-site recording above shows the same events
>   via the trace timeline as post-run real data.

Goal: run the full Crucible verification loop from the terminal (and as a Claude
Code slash command), with **no web app required**. Observability is the headline
feature: every step streams to the terminal as it happens AND lands in durable,
replayable artifact files. A thin static site later renders those files, so the
dashboard can never show a number a run did not actually write (this structurally
kills the facade class documented in `FACADE_AUDIT.md`).

This is a goal loop: build one slice, satisfy its done-criterion, move on. Each
slice reuses the existing deterministic core (`orchestrator/loop.py`, the oracle
ensemble, red/blue agents); we are adding a CLI front-end and an observability
spine, not rewriting the verifier.

**Spec-driven (CATA-anchored).** This checklist is the `tasks.md` of the slash
command. The source of truth is the CATA set in the repo root: `coding-practices.md`
(how we build), `ARCHITECTURE.md` (the CLI topology), `acceptance-tests.md` (what
"done" means, in CLI terms), and `QA_ADVERSARY.md` (how it is attacked). Slice 00
brings those docs in line with the CLI direction BEFORE any code; every later
slice cites the acceptance test it satisfies and the architecture component it
touches. If this checklist and the CATA docs ever disagree, the CATA docs win and
this file is re-synced.

---

## The observability contract (build this FIRST — everything else emits through it)

Reference pattern we liked: `tax-filing-agent/server/logger.ts`. One writer,
multiple sinks, append-only, typed events, the same record to file and stdout:

```ts
// tax-filing-agent/server/logger.ts:26-35  (the model)
// Append one event to the session's JSONL trail and echo it to stdout so the log
// viewer carries the same record. Append-only, never rewritten.
export function logEvent(sessionId, type, data): TraceEvent {
  const event = { ts: Date.now(), type, data };
  appendFileSync(tracePath(sessionId), JSON.stringify(event) + '\n');
  console.log(JSON.stringify({ sessionId, ...event }));   // structured stdout
  return event;
}
```

Crucible's version (Python, since the core is Python) is one `emit(run_id, type,
data)` with THREE sinks from a single call:

1. **Durable artifact**: append one line to `artifacts/runs/<run_id>/trace.jsonl`
   (append-only, never rewritten, the grader-readable source of truth).
2. **Raw structured stdout**: one `json.dumps` line per event (machine/log-viewer).
3. **Pretty live terminal**: a human renderer (round headers, colored oracle
   vote lines, running ASR / recall / spend) driven off the same event, behind a
   `--stream human|json|both` flag. Never a second code path that can drift.

Typed event union (closed set, exhaustively matched, mirrors the loop stages):

```
run_start · eligibility_checked · suitability_assessed · run_rejected ·
spec_sealed · round_start ·
red_tactic_proposed · target_queried · target_scored ·
oracle_fired (one per oracle, with pass/fail + reason) · verdict ·
catalog_hit (undetected hack logged) · blue_patch_proposed · blue_retrained ·
holdout_validated · metric_update (asr/recall/gap/spend) · halt_check ·
artifact_written (path + kind) · run_end
```

Every event: `{ ts, run_id, type, seq, data }`. `seq` is a monotonic counter so
the file is totally ordered even if two events share a millisecond.

### Emoji glyphs per event type (terminal + site)

The 1040 agent gave every event type a glyph in its trace panel
(`tax-filing-agent/client/src/TracePanel.tsx`: `🔧` tool call, `✓`/`✗` pass/fail,
`🛑` guardrail block, `📄` produced doc, `💬` assistant, `▶` start). We keep that.
Each `EventType` maps to ONE glyph, defined once next to the enum so the terminal
renderer and the static site read from the same table (no drift):

```
▶ run_start        🔎 eligibility_checked   🧭 suitability_assessed  🚫 run_rejected
🔌 adapter_scaffolded                        🔒 spec_sealed
🥊 round_start     🎯 red_tactic_proposed   📡 target_queried   📊 target_scored
🟢 oracle pass     🔴 oracle fail           ⚖️ verdict          🧠 catalog_hit
🔧 blue_patch      ♻️ blue_retrained        🛡️ holdout_validated 📈 metric_update
🛑 halt_check      📄 artifact_written      🏁 run_end
```

Glyphs are decoration on top of the structured record; the JSONL `type` field
stays plain text so `jq` and graders are never parsing emoji. A `--no-emoji` flag
falls back to ASCII tags for terminals that mangle wide glyphs.

### Paths are surfaced, every time

Whenever a file is written, `emit` fires an `artifact_written` event carrying the
**absolute path** and the kind, and the human renderer prints it as an openable
line. At `run_end` the terminal prints a "Artifacts" block listing every produced
doc with its absolute path (and a one-key `crucible report --open <run_id>` to
open the rendered site). From the slash command, the same paths come back as
clickable `computer://` links via `present_files`, so the produced docs are one
click away, never a path the user has to hunt for.

---

## Per-component test matrix (evals vs unit tests)

Two kinds of components, two kinds of proof. A component whose behavior is an LLM
judgment is non-deterministic, so it gets an **eval**: a fixed dataset, a metric,
and a threshold, measured on real runs (never stubbed). A deterministic tool gets
a **unit test**: same input, same output, asserted exactly. Every component lands
in exactly one column.

| Component | Module | Proof | Eval metric / unit assertion |
|---|---|---|---|
| Red search agent | `modules/red/search` | **eval** | attack-success-rate on a fixed target+seed set; finds the known evasions; refusal-rate; $/success |
| Hybrid fallback | `modules/red/hybrid` | **eval** | scipy sweep finds the evasion region on a fixture detector within budget |
| White-box brief | `modules/red/white_box` | **eval** | white-box recall ≤ black-box recall on the same target (the gap is the measured quantity) |
| Blue proposer | `modules/blue/proposer` | **eval** | proposed patch recovers detection on a held-out missed set; patch is valid/applies |
| Code-agent producer | `modules/targets/code_agent` | **eval** | emitted source is `ast.parse`-able on a task set; score == 1.0 rate |
| Suitability advisor | `crucible/suitability` | **eval** | agreement with a labeled set of ideal / workable / poor-fit targets; warnings match the known consequence |
| Adapter authoring agent | `crucible/adapter_scaffold` | **eval** | generated adapter implements the `Target` protocol, passes its health self-test, and clears eligibility on a sample-target set |
| Demo-authenticity observer | `crucible/demo_observer` | **eval** | every on-screen claim ties to a real artifact in the recording window; flags reuse / mock / edit / cherry-pick |
| Held-out oracle | `modules/oracles/held_out` | **eval** | generated tests fail known-bad outputs, pass known-good (precision/recall of the catch) |
| Metamorphic oracle | `modules/oracles/metamorphic` | **eval** | relations hold on a correct impl, break on a seeded-buggy impl |
| Differential oracle | `modules/oracles/differential` | **eval** | second-impl disagreement flags divergent outputs, stays quiet on agreeing ones |
| Property-fuzz oracle | `modules/oracles/property_fuzz` | **eval** | finds a counterexample on seeded-buggy, none on correct |
| LLM judge oracle | `modules/oracles/llm_judge` | **eval** | agreement with ground-truth labels on a labeled set (judge-alone precision/recall) |
| Aggregator | `modules/oracles/aggregator` | **unit** | weighted tally, pass threshold, exact vote math |
| Producer sandbox | `shared/sandbox` | **unit** | strips env, denies network egress, returns `{stdout,exit_code}` |
| Metrics | `modules/measure/metrics` | **unit** | asr/recall/gap math; null (not 0.0) when unmeasured |
| Halt rule | `modules/measure` (`should_halt`) | **unit** | halts iff recall < threshold |
| Retrainer | `modules/blue/retrainer` | **unit** | version increment, new `.lgb`/config emitted, vendor model untouched |
| Holdout validator | `modules/blue/holdout_validator` | **unit** | contamination guard rejects overlapping sets; detection-rate math |
| Fraud scorer | `modules/targets/fraud` | **unit** | booster loads, scores a known record to a known band |
| Strategy catalog | `modules/red` (`StrategyCatalog`) | **unit** | append-only, reuse-count increments, survives runs |
| Spec parser | `shared/types/sealed_spec` | **unit** | YAML → SealedSpec; each malformed case throws its specific typed error |
| Eligibility | `crucible/eligibility` | **unit** | each ineligible reason returns its typed verdict + fix |
| Obs emit / trace | `shared/obs/emit` | **unit** | append-only, ordered, monotonic `seq`, three sinks |
| Report renderer | `crucible/report` | **unit** | renders only from files; no numeric literal in metric slots |

Rule: a component may not be marked done until its row's proof is green. Evals run
on real LLM calls (opt-in flag for cost), unit tests run in CI with no network.

## Slices

### Slice 00 — Spec-driven foundation (CATA, do this FIRST, before any code)
- [ ] Update `ARCHITECTURE.md`: add the CLI topology (slash command → eligibility
      → suitability → loop via the existing `MeasureSink` seam → artifact files →
      static renderer) and FIX the two known doc/code drifts surfaced in the audit:
      the sandbox is **Docker** (`shared/sandbox/docker_sandbox.py`), not Modal; and
      there is **no** `modules/targets/research_agent/` (the real third registered
      target is `dummy`).
- [ ] Regenerate `acceptance-tests.md` user stories in CLI terms (the existing ones
      are phrased as web clicks): e.g. "As an operator, I run `crucible run` against
      a target and get a verdict, a streamed trace, and a report file." Each later
      slice references one of these by id.
- [ ] Confirm `coding-practices.md` and `QA_ADVERSARY.md` are populated (not the
      verbatim template) and cover the CLI paths.
- [ ] Decide and record the web-app disposition here (kept / deprecated / replaced
      by the static renderer) so two front-ends do not silently diverge.
- [ ] **Done:** the four CATA docs describe the slash command, contain no template
      placeholders, and name the Docker sandbox and the real `dummy` target; the
      placeholder-grep from the project workflow prints nothing.

### Slice 0 — CLI scaffold, no web dependency
- [ ] `crucible/cli.py` entrypoint exposed as `python -m crucible` and a console
      script `crucible`. Subcommands stubbed: `run`, `replay`, `report`,
      `catalog`, `status`.
- [ ] Core imports succeed with **no** FastAPI/uvicorn/Render import on the path
      (the loop is already web-agnostic: `orchestrator/loop.py` "carries no
      business logic: it calls interfaces in sequence"). Persistence target is a
      run directory of files; Postgres optional, not required.
- [ ] **Done:** `crucible --help` lists all subcommands; `python -c "import
      orchestrator.loop"` works without starting a server.

### Slice 0.5 — Prerequisites gate (runtime, secrets, data)
- [ ] `crucible doctor` verifies what a real run needs and reports each with a
      specific fix, never a vague failure: the Claude CLI is on PATH and authed;
      **Docker is running IF a code-shaped target is selected** (the producer
      sandbox is `docker run --network none`; a fraud-only run does not need it);
      the real model artifacts exist (`artifacts/fraud-v1.lgb`, `fraud-v2.lgb`); the
      fraud dataset is fetchable (`scripts/fetch_fraud_dataset.py`); and the eval
      datasets (labeled sets for the judge/oracle evals) are present.
- [ ] **Local runs MUST use the Claude CLI (Claude Max), not a metered API key.**
      `make_llm` (`shared/llm/__init__.py`) must return a CLI-backed `LLMClient`
      (shell out to `claude -p`) whenever the `claude` binary is present, and only
      fall back to `AnthropicClient` / `ANTHROPIC_API_KEY` when it is absent (the
      Render deploy, which has no CLI). Today `make_llm` only knows the API key and
      OpenRouter, so a local run with no key pops the `ANTHROPIC_API_KEY` prompt even
      though the CLI is available; that is the bug to fix. The deploy keeps the API
      path; the local slash command must not.
- [ ] `crucible doctor` reports which provider is ACTIVE (cli vs api), not merely
      that the `claude` binary exists, so a CLI-present-but-unused state is visible.
- [ ] Any missing secret is requested via the macOS hidden-input popup (never a
      terminal prompt or a file edit), per the project's secrets discipline; but the
      `ANTHROPIC_API_KEY` popup must NOT appear locally when the CLI is available.
- [ ] **Done:** `crucible doctor` prints a green/red line per prerequisite incl. the
      active LLM provider; with the `claude` binary present and no API key set,
      `crucible run` completes a real run through the CLI and never prompts for
      `ANTHROPIC_API_KEY`; the key is requested only when the CLI is absent.

### Slice 1 — Observability spine (priority)
- [ ] `shared/obs/emit.py`: `emit(run_id, type, data)` writes the JSONL line,
      the raw stdout line, and feeds the pretty renderer. Closed `EventType` enum,
      `match` without `default` so a new stage forces a compile-time decision.
- [ ] `read_trace(run_id)` reads the append-only file oldest-first (mirror of the
      1040 `readTrace`).
- [ ] Clear, specific errors: if the run dir is unwritable, raise a typed
      `TraceSinkUnwritableError` naming the path and the fix, never a silent drop.
- [ ] Each `EventType` has a glyph in the single glyph table; `--no-emoji` swaps
      to ASCII tags. `artifact_written` events carry the absolute path.
- [ ] **Wire it through the existing seam, not beside it.** The loop already emits
      through the `MeasureSink` Protocol (`orchestrator/interfaces`). Implement the
      observability/artifact emitter AS a `MeasureSink` so it is the same path the
      mainline drives, and decide per Slice 00 whether the Postgres sink stays
      (dual-sink) or the file sink replaces it. No second emit path.
- [ ] Each event carries a `schema_version` so a future `EventType` change does not
      silently break `read_trace` on old traces.
- [ ] **Done:** a unit test calls `emit` with one of each `EventType`, then
      `read_trace` returns them in order with monotonic `seq`; stdout shows both a
      JSON line and a human (glyph) line; the JSONL `type` field is plain text.

### Slice 1b — Target eligibility pre-flight gate
- [ ] `crucible/eligibility.py`: `check_eligibility(target_type, artifact_ref,
      spec) -> Eligibility` runs BEFORE any LLM spend and classifies the target as
      `ELIGIBLE`, `ELIGIBLE_WITH_CAVEAT`, or `INELIGIBLE`. Reuses the existing
      adapter registry and target health self-tests; no new verification logic.
- [ ] Ineligible reasons, each a typed error naming the exact fix (not a generic
      message):
      - unknown target type (no adapter registered)
      - Shape 1 artifact missing / unreadable / checksum mismatch (`.lgb` not found)
      - Shape 2 endpoint or config unreachable, or the target health self-test fails
      - spec does not parse, has zero obligations, or an unknown
        `holdout_generator_kind` (oracles cannot be derived)
      - `spec.target` does not match the chosen target type
      - target is a stub (e.g. research_agent returns `{status: "stub"}`)
      - required runtime missing: Claude CLI unreachable, or the producer sandbox
        runtime is unavailable
- [ ] Caveat (not a rejection): the four mechanical oracles assume code-shaped
      output, so a Shape-1 classifier is `ELIGIBLE_WITH_CAVEAT` and runs the
      judge-plus-score subset. The gate states the reduced ensemble up front so the
      operator is not surprised by a thinner verdict.
- [ ] Emits `eligibility_checked` with the verdict + reasons, writes
      `artifacts/runs/<run_id>/eligibility.json`, and on `INELIGIBLE` emits
      `run_rejected` and exits non-zero WITHOUT spending a cent on the loop.
- [ ] **Done:** pointing `run` at a missing `.lgb` prints the specific reason and
      the fix, writes `eligibility.json`, spends $0, and exits non-zero; a healthy
      `code_agent` passes the gate and proceeds.

### Slice 1c — Target suitability advisor (soft, agentic, never halts)
- [ ] `crucible/suitability.py` hosts a dedicated agent (separate from the
      eligibility gate) that judges whether a target is a GOOD FIT, not whether it
      can run. Output: `Suitability { grade: IDEAL | WORKABLE | POOR_FIT,
      warnings: [{ reason, consequence_if_run_anyway, mitigation }] }`.
- [ ] It **never halts**. It emits `suitability_assessed` (one warning line each,
      glyph 🧭), writes `artifacts/runs/<run_id>/suitability.json`, and the run
      proceeds. The grade is printed in the report header so a reader does not
      over-trust a `POOR_FIT` verdict.
- [ ] The agent pairs deterministic signals (obligation/invariant count, which
      oracles actually apply, task triviality) with an LLM judgment about whether
      the catch rate will be MEANINGFUL. Pre-baked warning shapes, each with its
      "what happens if you run anyway":
      - few/no invariants → "oracles have little to check, a near-100% pass rate is
        uninformative, not evidence of correctness."
      - fraud classifier → "only the judge and score-threshold vote; the four
        mechanical oracles don't apply, so the verdict rests on one weighted
        opinion and recall is softer than a code target's."
      - trivial/closed-form task → "the red agent has almost no surface to
        reward-hack, so a clean run doesn't show Crucible caught anything hard."
      - out-of-scope concern (leak/uptime) → "Crucible only checks Integrity;
        running produces an Integrity verdict that won't answer your question."
- [ ] **Done:** running against a 1-obligation spec proceeds (no halt) but prints a
      🧭 `POOR_FIT` warning with the reason and the run-anyway consequence, and
      `suitability.json` carries it; the report header shows the grade.

### Slice 1d — Per-project adapter authoring agent (target-agnostic onboarding)
- [ ] `crucible adapter scaffold --project <name> --kind <shape1|shape2>
      [--artifact <.lgb> | --endpoint <url> --config <file>] --task "<desc>"`: a
      dedicated agent generates a per-project adapter under
      `modules/targets/<project>/` that implements the existing `Target` protocol
      (the same `query_target()/submit()` surface the loop already uses) plus its
      health self-test, and registers it in the same wiring.
- [ ] The generated adapter wraps the target **inside the existing producer
      sandbox** (network-sealed, env-stripped); the agent may not weaken that
      boundary. It scaffolds the adapter and the sealed-spec template, nothing that
      touches the verification answer key.
- [ ] Emits `adapter_scaffolded` (glyph 🔌) with the new module path, then runs the
      Slice 1b eligibility gate against it so a bad scaffold is caught immediately.
- [ ] **Done:** `crucible adapter scaffold --project acme-fraud --kind shape1
      --artifact acme.lgb` produces a real adapter module that passes
      `/health/targets/...` (the round-trip self-test) and clears the eligibility
      gate, with no edit to the core loop.

### Slice 2 — Headless run driver
- [ ] `crucible run --target <fraud|code_agent> --spec <file.yaml> --rounds N
      --max-dollars D` runs the Slice 1b eligibility gate FIRST, then (only if not
      `INELIGIBLE`) drives the existing loop end-to-end (red → verify → harden →
      measure) against real LLMs via the local Claude CLI.
- [ ] Every loop stage calls `emit` (no stage runs silently). Reuse the real
      modules; **no stub/sample data** anywhere in the path.
- [ ] Cost discipline: spend is surfaced live in `metric_update`; `--cap-preview`
      runs ~1 minute (or N rounds) and stops for operator confirmation before a full
      run; the inner loop caches and batches LLM calls where it can (the PRD's
      "per-loop cost" caveat). The `--max-dollars` ceiling halts the run with a
      clear `BudgetExceeded` event, never a silent stop.
- [ ] **Done:** a real `code_agent` run produces a non-empty `trace.jsonl` whose
      event sequence contains at least one `oracle_fired` per registered oracle and
      exactly one `verdict` per produced output; the terminal showed the run live.

### Slice 3 — Artifact file layout (the "documents produced over time")
- [ ] Per run, write under `artifacts/runs/<run_id>/`:
      `trace.jsonl` (full event stream), `verdicts/<verdict_id>.json` (output +
      each oracle's vote + tally + replay seed), `metrics.json` (asr/recall/gap/
      spend, real measured values or explicit null, never 0.0 as a placeholder),
      `catalog.jsonl` (undetected tactics, append-only, outlives the run),
      `report.md` (human run summary), `sr-117.md` (model-risk report).
- [ ] A top-level `artifacts/runs/index.jsonl` appends one row per run for history.
- [ ] **Done:** after a run, every file above exists and is non-empty; `metrics.json`
      numbers equal what `read_trace` last `metric_update` carried (no divergence).

### Slice 4 — Terminal observability UX
- [ ] Human renderer: a round banner with absolute local timestamp (not an elapsed
      counter), the per-event glyph from the single glyph table, one colored line
      per oracle vote (🟢/🔴), a running `ASR / recall / spend` footer, and the red
      agent's reasoning streamed as it arrives.
- [ ] On every `artifact_written` and at `run_end`, print an "Artifacts" block
      listing each produced doc by absolute path, plus the `crucible report --open
      <run_id>` convenience.
- [ ] `--stream json` emits only the raw lines (for piping); `--stream both` does
      both; default `human`.
- [ ] **Done:** running with `--stream human` shows live per-oracle votes and a
      live recall number; piping `--stream json | jq .type` lists the stage
      sequence.

### Slice 5 — Deterministic replay from files
- [ ] `crucible replay <run_id> <verdict_id>` re-runs the verification ensemble
      against the stored producer output and asserts byte-equality with the
      persisted verdict (the existing replay guarantee:
      "with deterministic oracles the replay is byte-equal").
- [ ] Emits a `verdict` event tagged `replay=true` plus a `diff` event; writes
      `verdicts/<id>.replay.json`.
- [ ] **Done:** replay of a real verdict prints `byte-equal: true` and the diff
      file shows tally delta `< 1e-9`.

### Slice 5b — Component focus-fix subcommands (the SAME object the mainline calls)
- [ ] Every component is invocable in isolation so a broken one is fixed without
      running the whole loop: `crucible oracle run --name held_out --output <file>
      --spec <file>`, `crucible red propose --target <t> --transcript <file>`,
      `crucible blue propose --missed <file>`, `crucible eligibility check ...`,
      `crucible suitability check ...`, `crucible adapter scaffold ...`,
      `crucible verdict aggregate --votes <file>`, `crucible metrics compute --run
      <id>`, `crucible eval <component>`.
- [ ] **Single code path (non-negotiable).** Each subcommand resolves the
      component through the **same registry/wiring the loop uses** and calls the
      same protocol method. No parallel "CLI version" of any component. A change to
      a component is seen identically by the loop and by its subcommand.
- [ ] **Done:** a test asserts the object the loop resolves for component X and the
      object the `crucible <x>` subcommand resolves are the same wiring path (a
      change to the module is observable through both, proven by one shared fixture
      run twice). Running `crucible oracle run --name metamorphic` reproduces that
      oracle's exact behavior from a real loop round in isolation.

### Slice 6 — Static report site = pure renderer (kills the facade class)
- [ ] `crucible report --run <id>` (and `--all`) generates a static `site/` that
      reads ONLY the artifact files: trace timeline, per-verdict drill-down, recall
      vs halt line, catalog table, AND the PRD Pillar-4 views — attack-success-rate
      and detection-rate curves across rounds, the red/blue co-evolution curve
      (convergence vs oscillation), and the strategy leaderboard (discovered cheats
      ranked, the exported reusable benchmark). Every curve and rank is computed
      from `trace.jsonl` / `catalog.jsonl`; zero hardcoded numbers.
- [ ] If a metric file is absent, render "Not yet measured", never a literal.
- [ ] **Done:** `grep` for any numeric literal in the rendered metric slots returns
      nothing; deleting a `metrics.json` flips that card to "Not yet measured".

### Slice 7 — Integrity separation (do not skip)
- [ ] Verification executes where the producer cannot read the sealed spec or the
      held-out generator (the existing producer sandbox: network-sealed, env-
      stripped). Document in the README that the **operator runs `/crucible`, not
      the producer**; if the producer self-runs, the spec/holdout must still run in
      a sandbox out of their process.
- [ ] The sealed spec and holdout instances never appear in `trace.jsonl` before
      submission (assert this in a test).
- [ ] **Done:** a test confirms no pre-submission event carries holdout instances;
      the sandbox still strips network/env in the CLI path.

### Slice 8 — Slash command surface
- [ ] `~/.claude/skills/crucible/SKILL.md` so `/crucible` invokes the CLI: parse
      target/spec/rounds, run, then surface the run dir + `report.md` as clickable
      artifacts.
- [ ] Long runs: if a run will exceed the turn, write progress to `trace.jsonl`
      and schedule a follow-up to deliver the finished report (your standard
      long-wait pattern), rather than blocking.
- [ ] **Auto-scaffold on unknown target.** When the eligibility gate returns
      `INELIGIBLE` with reason code `unknown_target`, the slash command automatically
      invokes `crucible adapter scaffold` (Slice 1d) to generate the adapter, registers
      it, re-runs the eligibility gate, and proceeds with the run if the re-check passes.
      The operator sees the scaffold event (`adapter_scaffolded`) in the trace, not a
      rejection. A manual `crucible run` from the bare CLI still rejects with the fix
      message (the auto-scaffold is a slash command convenience, not a CLI behavior change).
- [ ] **Done:** `/crucible run code_agent sum-two-ints.yaml --rounds 6` streams in
      chat and returns the report file link. `/crucible run <unknown_target>` scaffolds
      the adapter, reports the scaffold, and proceeds (or fails on the re-check with
      a specific reason).

### Slice 8b — Per-component eval harness
- [ ] `crucible eval <component>` runs that component's eval (dataset + metric +
      threshold) from the test matrix, on real LLM calls, and writes
      `artifacts/evals/<component>/<ts>.json` plus a one-line pass/fail with the
      measured number vs the threshold. `crucible eval --all` runs the suite.
- [ ] Eval datasets are real (recorded inputs + ground-truth labels), never
      synthetic placeholders. A missing dataset is a typed error naming the path,
      not a silent skip.
- [ ] The eval invokes the component through the same wiring as Slice 5b, so an
      eval is a focus-run with a scored oracle attached.
- [ ] **Done:** `crucible eval llm_judge` prints judge-alone precision/recall vs
      threshold from a real labeled set and writes the eval artifact.

### Slice 9 — QA gate
- [ ] Unit tests green for every **unit** row of the test matrix (no network, CI).
- [ ] Evals green (above threshold) for every **eval** row; the eval artifacts are
      committed so a regression in an LLM component is visible as a number drop.
- [ ] Golden run test: a fixed seed produces a `trace.jsonl` whose stage sequence
      matches a committed fixture (observability completeness: every loop stage
      emitted, including `eligibility_checked` and `artifact_written`).
- [ ] Same-code-path test (Slice 5b) green: subcommands and loop resolve identical
      components.
- [ ] No-stub check: grep the CLI/eval paths for mock/sample/placeholder data; must
      be clean.
- [ ] Replay byte-equal test in CI.
- [ ] **Done:** every matrix row's proof is green and all gate tests pass.

### Slice 10 — Authentic demo video (human POV, real models, nothing mocked)
- [ ] Record an end-to-end demo of a FRESH LIVE run from the operator's point of
      view: an actual screen + terminal capture of a person driving `/crucible`,
      with real cursor, real timing, and real streaming output. Not a
      reconstructed, re-narrated, or agent-puppeted walkthrough.
- [ ] **Nothing mocked, stubbed, replayed, cached, or reused.** `MOCK_LLM` is off,
      real Claude CLI, real oracles, real sandbox. The run in the video is captured
      live; if any shown result is not fresh and real, it is not used (the
      no-fake/no-reused-data rule; the Sivraj 2026-05-28 reused-audio incident is
      the exact failure this forbids).
- [ ] Test against the ML models Crucible has ALREADY trained and used: the
      committed `artifacts/fraud-vN.lgb` fraud classifier and the real code agent,
      not a toy model spun up for the camera.
- [ ] The recording shows the full loop live: eligibility + suitability, sealed
      spec, red attacks with the reasoning stream scrolling, per-oracle votes, a
      real verdict, one blue-hardening round with detection recovering, the metrics,
      and the produced artifact files opened from their real paths.
- [ ] If uploaded, default to Unlisted; link the video and its run dir together.

#### Anti-reward-hacking observer (guards the demo against gaming itself)
- [ ] A dedicated **demo-authenticity observer agent** watches the video-creation
      strategy and certifies that the result genuinely emulates an authentic user
      experience, rather than gaming the demo to look good. This is Crucible's own
      anti-reward-hacking premise applied to ourselves.
- [ ] It refuses to sign off on any reward-hacking pattern: reusing a prior
      capture, swapping in mock/stub data, hand-editing artifacts to look cleaner,
      fast-forwarding past a failure, cherry-picking a lucky take while hiding
      failed ones, or narrating claims the artifacts do not support.
- [ ] Every on-screen claim must tie to a real artifact produced during the
      recording window: a `trace.jsonl` event, or a file whose hash and mtime fall
      inside the capture's time range. Any claim that cannot be tied out fails.
- [ ] It judges the SPIRIT, not a checkbox: the question it answers is "would a
      real first-time operator, running this honestly, see what the video shows?"
- [ ] **Done:** the observer emits an authenticity report mapping each on-screen
      moment to its backing artifact; the report is clean (no reused / mocked /
      edited evidence), the run provably used the real `fraud-vN.lgb` and code
      agent, and `MOCK_LLM` was provably off for the captured run.

---

## Build order and whole-loop definition of done

Order (dependencies): **00** (CATA) → **0** (scaffold) → **0.5** (doctor) →
**1** (observability spine, the `MeasureSink`) → **1b/1c/1d** (gates + agents, can
parallelize) → **2** (run driver) → **3** (artifacts) → **4** (terminal UX) →
**5** (replay) → **5b** (focus subcommands) → **6** (static site) → **7**
(integrity) → **8** (slash surface) → **8b** (evals) → **9** (QA gate) → **10**
(authentic demo). Slices 1b, 1c, 1d, 4, and 5b can run in parallel once 1 lands.

The whole loop is done only when ALL of the following hold:
- [ ] The four CATA docs describe the CLI and carry no template placeholders.
- [ ] `crucible doctor` is green for a real code-agent run (Docker up, CLI authed,
      real models + datasets present).
- [ ] A fresh real run produces a complete `trace.jsonl`, the artifact files, and a
      static report whose every number traces to a file (no facade).
- [ ] Every test-matrix row is green (unit tests for deterministic tools, evals
      above threshold for the LLM components), and the same-code-path test passes.
- [ ] Replay is byte-equal; the integrity wall holds (no pre-submission holdout in
      the trace; produced code runs only in the Docker sandbox).
- [ ] A user-facing quickstart exists (install, `crucible doctor`, first run,
      where the artifacts land) and `crucible run --target dummy` is a zero-cost,
      no-Docker smoke test that exercises the whole pipeline.
- [ ] The authentic demo video passes the anti-reward-hacking observer.

## Why this is the honest implementation

The artifact files ARE the deliverable. The terminal stream and the static site
are two renderers of one append-only event log, exactly the 1040 pattern, so they
cannot disagree with each other or invent data. Everything a viewer sees was
written by a real run, which is the property the web dashboard failed to hold.
