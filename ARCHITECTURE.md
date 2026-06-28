# ARCHITECTURE

How Crucible is structured as a `/crucible` slash command and command-line tool. This is the
"A" of the CATA set. The acceptance tests (`acceptance-tests.md`) define what "done" means against
this topology, and `SLASH_COMMAND_GOAL_LOOP.md` (the tasks list of this effort) cites the components
named here.

Crucible is an adversarial verification platform. It catches silently wrong AI outputs, the
"Integrity" pillar. It does not address Confidentiality or Availability. The mature deterministic
core (the red, verify, harden, measure loop, the oracle ensemble, the red and blue agents) already
exists in Python. This effort adds a command-line front end and an observability spine on top of that
core. It does not rewrite the verifier.

---

## 1. The one-line shape

```
/crucible (slash command)
   -> crucible CLI (package crucible/)
        -> eligibility gate            (crucible/eligibility.py: can this target run at all?)
        -> suitability advisor         (crucible/suitability.py: is this target a good fit? never halts)
        -> orchestrator loop           (orchestrator/loop.py: red -> verify -> harden -> measure)
             driven through the EXISTING MeasureSink seam
             now implemented by FileTraceSink (shared/obs/sink.py + shared/obs/emit.py)
        -> artifact files              (artifacts/runs/<run_id>/: trace.jsonl, verdicts/, metrics.json,
                                        catalog.jsonl, report.md, sr-117.md)
        -> static renderer             (crucible report: pure renderer over the artifact files)
```

Two renderers read one append-only event log: the live terminal stream and the static site. Because
both render the same `trace.jsonl`, they cannot disagree with each other or invent a number a run did
not write. That is the property the prior web dashboard failed to hold, and it is the structural fix
recorded in section 6.

---

## 2. Component-by-component breakdown

Every row names the component, what it is responsible for, what flows in, what flows out, where it
persists, and how it fails. Paths are real and verified against the code on the `feat/slash-command`
branch.

| Component | Responsibility | Inputs | Outputs | Persistence | Failure modes |
|---|---|---|---|---|---|
| Slash command surface (`~/.claude/skills/crucible/SKILL.md`, Slice 8) | Parse `/crucible run ...` in chat, invoke the CLI, surface the run dir and `report.md` as clickable artifacts | Chat text: target, spec, rounds, budget | A CLI invocation; clickable `computer://` artifact links via `present_files` | None of its own (delegates to the CLI) | Malformed chat args surface as the CLI usage error; a run that exceeds the turn writes progress to `trace.jsonl` and schedules a follow-up rather than blocking |
| CLI entrypoint (`crucible/cli.py`, exposed as `python -m crucible` and console script `crucible`, Slice 0) | Dispatch subcommands: `run`, `replay`, `report`, `doctor`, `eligibility`, `suitability`, `catalog`, `status`, plus the focus subcommands (`oracle`, `red`, `blue`, `verdict`, `metrics`, `eval`, `adapter`) | argv | Subcommand dispatch, process exit code | None | Unknown subcommand prints usage and exits non-zero; core imports must succeed with no FastAPI or uvicorn on the path (the loop is web-agnostic) |
| Prerequisites doctor (`crucible doctor`, Slice 0.5) | Verify what a real run needs, each with a specific fix: Claude CLI on PATH and authed, Docker running IF a code-shaped target is selected, real model artifacts present (`artifacts/fraud-v1.lgb`, `fraud-v2.lgb`), the fraud dataset fetchable, the eval datasets present | Selected target type, environment | A green or red line per prerequisite, exit code | None | A missing prerequisite prints the exact fix command (for example the Docker start command); a fraud-only run reports Docker as "not required" |
| Eligibility gate (`crucible/eligibility.py`, Slice 1b) | Decide BEFORE any LLM spend whether a target can run: `ELIGIBLE`, `ELIGIBLE_WITH_CAVEAT`, or `INELIGIBLE`. Reuses the existing adapter registry and the target health self-tests, no new verification logic | Target type, artifact reference, sealed spec | An `Eligibility` verdict with typed reasons and fixes | `artifacts/runs/<run_id>/eligibility.json`; emits `eligibility_checked` | Each ineligible reason is a typed error naming the exact fix (unknown target type, missing or checksum-mismatched `.lgb`, unreachable Shape 2 endpoint, unparseable spec, spec target mismatch, stub target, missing runtime). On `INELIGIBLE` it emits `run_rejected`, spends zero, exits non-zero |
| Suitability advisor (`crucible/suitability.py`, Slice 1c) | Judge whether a target is a good fit, not whether it can run. Pairs deterministic signals (obligation and invariant count, which oracles actually apply, task triviality) with one LLM judgment about whether the catch rate will be meaningful | Sealed spec, target type, registered oracle set | A `Suitability` grade (`IDEAL`, `WORKABLE`, `POOR_FIT`) with warnings (reason, consequence if run anyway, mitigation) | `artifacts/runs/<run_id>/suitability.json`; emits `suitability_assessed` | It never halts. A `POOR_FIT` prints a warning line and the run still proceeds; the grade is printed in the report header so a reader does not over-trust a thin verdict |
| Adapter authoring agent (`crucible adapter scaffold ...`, Slice 1d) | Generate a per-project adapter under `modules/targets/<project>/` that implements the existing `Target` protocol plus its health self-test, and register it in the same wiring | Project name, shape (shape1 or shape2), artifact or endpoint, task description | A new adapter module and a sealed-spec template | The generated module on disk; emits `adapter_scaffolded` | The generated adapter wraps the target inside the existing producer sandbox; the agent may not weaken that boundary. A bad scaffold is caught immediately by running the eligibility gate against it |
| Orchestrator loop (`orchestrator/loop.py`) | Run the red, verify, harden, measure sequence. Per `constitution.md` section 2 it carries no business logic: it calls interfaces in sequence and emits each stage to the Measure sink | A wired `Container`, a sealed spec, round and budget limits | A stream of `MeasureSink.emit(run_id, kind, payload)` calls, verdicts, metrics | Postgres rows (legacy) plus, through the new sink, the artifact files | If a stage raises, the loop fails loud with a typed error rather than catch-log-continue; the `--max-dollars` ceiling halts with a clear budget event, never a silent stop |
| Interfaces / ports (`orchestrator/interfaces/`: `target.py`, `red.py`, `oracle.py`, `blue.py`, `measure.py`) | The five `typing.Protocol` ports the loop talks to. Modules implement them; modules never import each other | n/a (type contracts) | n/a | None | A protocol change rides its own branch through the orchestrator owner (`CONTRIBUTING.md` section 4) |
| Wiring / DI (`orchestrator/wiring.py`) | The ONLY module allowed to import both a concrete class and the interface it satisfies (`constitution.md` section 2). Builds the `Container`, registers targets, oracles, red and blue agents, health probes | Environment flags (`CRUCIBLE_REAL_*`), settings | A `Container` the loop and every focus subcommand resolve through (single code path, Slice 5b) | None | A missing fraud artifact downgrades the fraud health leaf to amber instead of failing startup; an unknown target kind raises a `KeyError` naming the registered kinds |
| Observability emitter (`shared/obs/emit.py`, the `Tracer`) | One `Tracer.emit(type, data)` call fans out to three sinks from a single point: the durable JSONL line, a raw structured stdout line, and the pretty terminal line. Holds the monotonic `seq` counter and the closed `EventType` enum with its single glyph table | An `EventType` and a payload | One `TraceEvent` appended to `trace.jsonl`, optionally echoed to stdout (`--stream json`) and the terminal (`--stream human`) | `artifacts/runs/<run_id>/trace.jsonl` (append-only, never rewritten) | If the run directory is unwritable it raises `TraceSinkUnwritableError` naming the path and the fix, never a silent drop |
| File trace sink (`shared/obs/sink.py`, `FileTraceSink`) | A `MeasureSink` that drives the `Tracer`. The loop already emits through the `MeasureSink` Protocol, so wiring this in means the file trace and terminal stream are produced by the exact same path the web run uses, never a second emit path that can drift | `MeasureSink.emit(run_id, kind, payload)` calls from the loop | Forwards verbatim to an inner sink (so the existing dashboard SSE and health route are untouched), then translates each legacy string kind into the closed `EventType` vocabulary | `trace.jsonl` (via the `Tracer`) plus the inner sink's state | Translation is total: an unknown kind is dropped to the inner sink only (informational), known kinds fan out; a single `verdict` fans into one `oracle_fired` per vote plus one `verdict` |
| Trace reader (`read_trace` in `shared/obs/emit.py`) | Read the append-only trace oldest-first (mirror of the reference logger's `readTrace`) | A run id or run dir | An ordered list of `TraceEvent` | Reads `trace.jsonl` | A missing trace file is an empty list (the run may not have started); a malformed line raises so corruption is never silently skipped |
| Artifact files (Slice 3) | The deliverable. Durable, replayable record of one run | The loop, through the sink | `trace.jsonl`, `verdicts/<verdict_id>.json`, `metrics.json`, `catalog.jsonl` (append-only, outlives the run), `report.md`, `sr-117.md`, plus the top-level `artifacts/runs/index.jsonl` history | `artifacts/runs/<run_id>/` under the root from `artifacts_root()` (overridable via `CRUCIBLE_ARTIFACTS_DIR`) | `metrics.json` carries real measured values or an explicit null, never `0.0` as a placeholder; an unwritable root surfaces `TraceSinkUnwritableError` |
| Replay driver (`crucible replay`, Slice 5) | Re-run the verification ensemble against the stored producer output and assert byte equality with the persisted verdict (with deterministic oracles the replay is byte-equal) | A run id and verdict id | A `verdict` event tagged `replay=true` plus a diff event | `verdicts/<id>.replay.json` | A non-deterministic divergence prints the tally delta and fails; the integrity wall still holds (no holdout leaks into the replay trace) |
| Static report renderer (`crucible report --run <id>` / `--all`, Slice 6) | Generate a static `site/` that reads ONLY the artifact files: trace timeline, per-verdict drill-down, recall versus halt line, catalog table, and the Pillar-4 curves (attack-success-rate and detection-rate across rounds, the red and blue co-evolution curve, the strategy leaderboard) | The artifact files of one or all runs | A static `site/` directory | `site/` | If a metric file is absent it renders "Not yet measured", never a literal; there is zero hardcoded number in any metric slot |
| Producer sandbox (`shared/sandbox/local.py`, `LocalDockerSandbox`) | Run producer-written code where it cannot read the sealed spec, the held-out generator, Postgres, or the internet. The seal is enforced by the kernel (no network interface), not by application code | A main script and supporting files | A `SandboxResult` (`stdout`, `stderr`, `exit_code`, `timed_out`, `network`) | A throwaway temp dir per job; optional `SandboxJobRow` via `record_sandbox_job` | A timeout kills the container and returns `timed_out=True`; if Docker is not running, a code-shaped run fails loud (the doctor catches this up front) |
| FastAPI web app (`orchestrator/api.py`) | Kept. The existing HTTP and SSE surface. See section 6 for its disposition | HTTP requests | SSE streams, health JSON | Postgres | Unchanged by this effort; the file sink forwards verbatim to the inner sink so the dashboard SSE keeps working |

---

## 3. End-to-end data flow for one `crucible run`

The primary use case. An operator runs one verification from the terminal.

1. **Invoke.** The operator runs `crucible run --target code_agent --spec sum-two-ints.yaml --rounds 6
   --max-dollars 5` (or `/crucible run code_agent sum-two-ints.yaml --rounds 6` from chat). The CLI
   constructs a run id and a `Tracer` whose run directory is `artifacts/runs/<run_id>/`.
2. **Emit run_start.** The `Tracer` writes the first `trace.jsonl` line and the terminal prints the
   round-zero banner.
3. **Eligibility gate (no spend yet).** `check_eligibility(target_type, artifact_ref, spec)` resolves
   the target through the same wiring registry the loop uses and runs the target health self-test. It
   emits `eligibility_checked` and writes `eligibility.json`. On `INELIGIBLE` it emits `run_rejected`,
   prints the specific fix, and exits non-zero having spent zero dollars. The run stops here on
   rejection.
4. **Suitability advisor (never halts).** `assess_suitability(...)` grades the fit, emits
   `suitability_assessed` (glyph the compass), and writes `suitability.json`. A `POOR_FIT` prints a
   warning and its run-anyway consequence; the run proceeds regardless.
5. **Seal the spec.** The spec compiler structures the operator's failure conditions into a
   `SealedSpec`; the loop emits `spec_sealed` with the obligation and invariant counts.
6. **Per round, red then verify.** For each round the loop emits `round_start`, the red agent proposes
   a tactic (`red_tactic_proposed`), the target is queried (`target_queried`) and scored
   (`target_scored`). Producer-written code, if any, runs inside `LocalDockerSandbox` (`docker run
   --network none`), sealed from the verification artifacts.
7. **Oracle ensemble votes.** The verify function runs the registered oracles. The single `verdict`
   payload fans, inside `FileTraceSink`, into one `oracle_fired` event per vote (green if the producer
   satisfied the check, red if the oracle caught a violation) plus one `verdict` event. Each
   `verdict.json` carries the output, every oracle's vote, the tally, and the replay seed.
8. **Catalog the misses.** Any undetected tactic appends a `catalog_hit` and a line to
   `catalog.jsonl`, which outlives the run.
9. **Harden (blue).** When the blue loop runs, the loop emits `blue_patch_proposed`,
   `blue_retrained`, and `holdout_validated`; the vendor model is never retrained (the system prompt
   or the config version changes).
10. **Measure.** `metric_update` carries the running attack-success-rate, recall, gap, and spend. The
    `--max-dollars` ceiling halts with a clear budget event; `halt_check` records the residual red
    line decision.
11. **Write artifacts.** Every file write fires `artifact_written` carrying the absolute path; the
    terminal prints it as an openable line. `metrics.json` is written from the last `metric_update`,
    so the file and the trace cannot diverge.
12. **End.** The loop emits `run_end`. The terminal prints an Artifacts block listing every produced
    document by absolute path plus the `crucible report --open <run_id>` convenience. From the slash
    command the same paths return as clickable links.
13. **Render (later, on demand).** `crucible report --run <run_id>` reads only the artifact files and
    writes a static `site/`. No number in the site is a literal; an absent metric renders "Not yet
    measured".

The three observability sinks all originate from `Tracer.emit`, the single fan-out point. There is no
other way to write a trace event, so the durable file, the raw stdout, and the pretty terminal can
never disagree.

---

## 4. Decisions table

| Decision | What we chose | Alternative considered | Why |
|---|---|---|---|
| Front end for the loop | A command-line tool plus a slash command, no web app required | Keep driving the loop only through the FastAPI dashboard | The loop is already web-agnostic (`loop.py` carries no business logic). A CLI removes the server dependency for a real run and makes the artifact files, not a live socket, the deliverable |
| Where events are written | One append-only `trace.jsonl` per run, three renderers off one `Tracer.emit` | A separate code path for terminal output and for the file | One writer with many sinks (the reference logger pattern) means the renderers cannot drift. A second emit path is exactly the facade risk we are killing |
| How the loop reaches the file | Implement the observability emitter AS a `MeasureSink` (`FileTraceSink`) | A new emit call placed beside the existing sink | The loop already emits through the `MeasureSink` Protocol; reusing that seam means the file trace is produced by the exact path the web run uses. No second path to keep in sync |
| Producer sandbox | Docker, `LocalDockerSandbox` in `shared/sandbox/local.py`, `docker run --rm --network none` | Modal (the original plan, now corrected) | The seal is enforced by the kernel (no network interface), proven by risk spike cr-r3 to block egress to both the host Postgres and the internet. It runs locally with no hosted-runtime dependency |
| Eligibility versus suitability | Two distinct stages: a hard gate that can reject, and a soft advisor that never halts | One combined check | The gate protects spend (reject before any LLM cost); the advisor protects trust (warn but proceed). Collapsing them would either block good runs or hide poor-fit warnings |
| Metric placeholders | Real measured value or explicit null, never `0.0` | Default an unmeasured metric to zero | A zero reads as a real measurement of "no attacks succeeded", which is a lie when nothing was measured. Null and "Not yet measured" are honest |
| Static site source | Pure renderer over the artifact files, zero hardcoded numbers | Render from a live database query | A renderer that reads only files cannot show a number a run did not write. Deleting a `metrics.json` flips its card to "Not yet measured", which proves the property |
| Web app disposition | Keep the FastAPI app; the artifact files plus static renderer are the new source of truth | Delete the web app | Both front ends render the same event log, so they cannot diverge. Removing the web app would lose the live SSE surface for no correctness gain (see section 6) |

---

## 5. Trade-offs

- **One append-only file per run.** We accept that a very long run produces a large `trace.jsonl`.
  It would bite if a single run emitted millions of events. The trigger to revisit is a run whose
  trace file is large enough to make `read_trace` slow; the fix is rotation or indexing, not a second
  writer.
- **Docker as a hard dependency for code-shaped targets.** We accept that a code-agent run needs a
  running Docker daemon. It bites an operator who forgot to start Docker. The mitigation is in place:
  `crucible doctor` checks the daemon up front and prints the exact start command, and a fraud-only
  run reports Docker as "not required".
- **Single code path for components.** We accept that every focus subcommand must resolve its
  component through the same wiring the loop uses (Slice 5b). It bites if someone adds a parallel "CLI
  version" of a component. The guard is a test that asserts the loop and the subcommand resolve the
  same wiring path; a change to a module is observable through both.
- **LLM judgments are non-deterministic.** We accept that the suitability advisor and the LLM-judge
  oracle cannot be unit-asserted exactly. The mitigation is the per-component test matrix in
  `SLASH_COMMAND_GOAL_LOOP.md`: deterministic tools get unit tests, LLM components get evals (a fixed
  dataset, a metric, a threshold) measured on real runs, never stubbed.
- **Two front ends.** We accept the cost of keeping the FastAPI app alongside the CLI and static
  renderer. It would bite only if the two rendered from different sources. They do not: both read the
  same event log, which is the whole point of section 6.

---

## 6. Web-app disposition (decided in Slice 00)

The FastAPI app at `orchestrator/api.py` is **KEPT**, not deprecated and not deleted.

The durable artifact files (`artifacts/runs/<run_id>/`) plus the static renderer (`crucible report`)
are the **new source of truth**. The two front ends, the live FastAPI dashboard and the static site,
must not diverge, and structurally they cannot, because both render the same append-only event log:

- `FileTraceSink` forwards every event verbatim to an inner `MeasureSink` (so the dashboard SSE and
  the `/health` route keep working unchanged) and also translates each event into the closed
  `EventType` vocabulary for `trace.jsonl`.
- The terminal stream, the static site, and the dashboard are all renderers over that one log.

This is the structural fix for the facade class documented in `FACADE_AUDIT.md`: a dashboard can no
longer show a number a run did not actually write, because every renderer reads the same file the run
appended to.

---

## 7. Two real doc and code drifts, corrected here

Slice 00 corrects two drifts that earlier documents carried. Both are verified against the source on
the `feat/slash-command` branch.

1. **The producer sandbox is Docker, not Modal.** Earlier text (for example `constitution.md` section
   1 and `SLASH_COMMAND_GOAL_LOOP.md`'s reference to `shared/sandbox/docker_sandbox.py`) named Modal
   or a `docker_sandbox.py` path. The real implementation is the class `LocalDockerSandbox` in
   `shared/sandbox/local.py`, which runs `docker run --rm --network none` against the
   `python:3.12-slim` image with a read-only code mount. The seal is enforced by the kernel, not by
   application code.

2. **There is no `modules/targets/research_agent/`.** The `modules/targets/` directory contains
   exactly `agent/`, `code_agent/`, `dummy/`, and `fraud/`. The targets registered in
   `orchestrator/wiring.py` (`build_container`) are: `dummy` (the zero-cost, no-Docker smoke target),
   `fraud` (the trained LightGBM classifier, registered only when its artifact loads), `agent` (the
   built-in support-bot demo, kind `"agent"`), and `code_agent` (writes Python and runs it in the
   Docker sandbox, kind `"code_agent"`). The research-agent target shape exists in the constitution as
   a deliberately stubbed, runtime-skipped adapter (`constitution.md` section 7); no
   `research_agent/` package is present and none is registered. The CLI `--target` examples in the
   plan use `fraud`, `code_agent`, and `dummy`, which are the three the operator drives day to day.


## Pillar 2b, Admissibility Referee (guarding the red agent's own score)

The red agent is an LLM optimizer, so its success metric is a proxy it can game
(see `RED_ADMISSIBILITY.md`). Two success criteria were unguarded: the fraud
evasion (`score < threshold`, no ground-truth label that the input is fraud) and
the code path (`undetected = verdict.passed`, no check the output is actually
wrong). The Admissibility Referee redefines a success as **(admissible attack) AND
(independently wrong output) AND (passed the verifier)**.

It uses deterministic and architectural anchors first (red can never edit the
sealed spec; fraud attacks must derive from a labeled-fraud seed; evasions must
replay deterministically; the catalog dedups), then a sealed, diverse committee of
cheap single-focus checkers for the semantic residue (coercion, in-distribution,
verifier prompt-injection, genuine-wrongness), gated on claimed successes only.

New metric in Measure: **red precision = genuine / claimed successes**, and its
complement the false-success rate, surfaced next to catch rate. The committee is
itself game-able; its criteria are sealed from the red agent and the white-box
self-test is extended to measure the committee's own false-pass rate. This shrinks
the false-success rate and makes it measurable, it does not make it zero.
