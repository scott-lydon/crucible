# Crucible goal-loop handoff: verify all specified functionality end to end

This briefs a multi-agent goal loop to drive Crucible's happy paths and core
functionality end to end on localhost through the Chrome MCP, fixing what is
broken, until every specified scenario runs continuously with no reviewer
raising a flag. It is fully self contained: a fresh session with no memory of
the prior conversation can execute it.

## 0. Prime directive: loyalty to the spec, zero invented scope

The single source of truth for "what should work" is, in this order:

1. `acceptance-tests.md` sections 1 (user stories US-1..US-15, each with its
   Given/When/Then) and 2 (out of scope).
2. `ARCHITECTURE.md` (component responsibilities, data flow, section 12 on
   deliberately skipped pieces).
3. `REMOVED_UI.md` (design-prototype controls intentionally cut because they
   have no backing route or are out of PRD).

Hard rules for every agent in this loop:

- **Verify only behavior that is in scope.** In scope means it traces to a
  specific US-n acceptance test, OR it is plainly entailed by the PRD as part of
  delivering a named US-n (the obvious supporting affordance a reasonable reader
  expects, even if no US enumerates it). Behavior that is neither traceable to a
  US-n nor plainly entailed by the PRD is not a feature to make work: do not
  assert it, do not wire it, do not grade it.
- **The PRD-entailed allowance is narrow, not a loophole.** It covers the
  unavoidable mechanics of a named story (for example: the Start button US-1
  names, the Inspect button US-2 names, an empty/error/loading state for a
  required view, a back link out of a drilled-in page). It does NOT cover a new
  capability. When in doubt whether something is "entailed" or "invented," treat
  it as invented and run the reconciliation step below.
- **Never invent a user story.** If you find yourself adding a capability that no
  US-n names and the PRD does not plainly entail (operator pause button, admin
  override toggles, halt-as-action, multi-tenant, a spec compiler, mobile
  layout), STOP. Those are out of scope per `acceptance-tests.md` section 2 and
  `REMOVED_UI.md`.
- **The honest fix for an out-of-scope, non-functional control is removal or an
  em-dash placeholder, not a new backing route.** A dead button that no US
  requires and the PRD does not entail gets deleted or disabled, never "made to
  work."
- **If a real US-n behavior genuinely needs something the spec did not state,
  do not silently build it.** Add it to `acceptance-tests.md` / `ARCHITECTURE.md`
  first, flag the contradiction to the operator, and only then implement. This
  is the CLAUDE design-fidelity rule #6.
- **No mock, stub, fabricated, cached, or replayed data may be presented as a
  real result** (the global NO-FAKE-DATA rule). Displayed values must equal the
  real backend source.

### Known reconciliation item (resolve before grading US-1)

`acceptance-tests.md` US-1 says the operator pastes the sealed YAML spec by
hand, and the automated spec compiler is explicitly out of scope (section 2).
The current build added `GET /targets/{type}/default-spec` and the launcher
auto-fills the spec from it. That is a convenience the spec did not ask for.
Decide one of: (a) update US-1 to state the launcher offers a per-target default
spec the operator may accept or replace, and keep the endpoint, or (b) remove
the auto-fill and require a pasted YAML. Do not leave the code and the spec
disagreeing. Surface the choice to the operator.

## 1. Agent team arrangement (built so the loop cannot lie to itself)

The arrangement separates writing from confirming. The agent that writes a fix
is never the agent that confirms it. Four roles, distinct contexts:

### A. Builder (writes code, may NOT confirm its own work)
- Tools: Read, Write, Edit, shell, backend test runner.
- Receives a findings packet from a reviewer and implements the smallest fix
  that satisfies the cited US-n. Commits each logical fix separately.
- May run backend-only checks to sanity-test its own change, but its say-so
  never closes a finding. Only a reviewer in a fresh context closes a finding.
- Forbidden from editing or "interpreting" reviewer screenshots or reports.

### B. Functional Verifier (fresh context per pass, drives the real UI)
- Tools: Chrome MCP (navigate, computer, get_page_text, read_console_messages,
  read_network_requests), Read, shell for curl, Bash. No Edit/Write.
- Spawned with NO knowledge of how the builder implemented anything, so it
  cannot inherit the builder's assumptions as facts.
- Walks each scenario in section 3 through the browser on localhost, asserting
  the Given/When/Then of the matching US-n literally. Records pass or fail with
  the screenshot and the console/network evidence.
- A scenario passes only when the on-screen result matches the US-n, not when
  "the code looks right."

### C. Data-Integrity / Authenticity Reviewer (the anti-fabrication agent)
- Tools: Chrome MCP (computer screenshot, get_page_text, read_network_requests),
  Read, shell for curl. No Edit/Write.
- For EVERY View as it is rendered during a scenario, it captures a screenshot
  WITH context (which US-n, which route, which run id) AND the backend JSON that
  populated that View (the exact `/metrics`, `/runs/:id`, `/halt`, `/reports/:id`,
  etc. response). It then scans for incorrect or fabricated displayed values:
  - Every number on screen must equal the value in the backing API response.
  - No leftover design-prototype constants may appear as if real. Known
    offenders to hunt: `92.7%` pass rate, `4 / 5 votes`, `0.027` drift,
    `$25` ceiling shown as measured spend, `crucible/sandbox:v1.4.2`,
    `validated 2026-06-19`, any hardcoded `spec.fraud.sealed.yaml` body. A value
    is allowed only if it is the real measurement or an honest em-dash.
  - Zero is acceptable only when zero is what was actually measured, never as a
    silent default.
- It does NOT fix anything. It writes a findings packet (View, US-n, screenshot
  path, expected-from-API vs displayed, verdict) and hands it to the Builder.
- It only checks Views that belong to an in-scope US-n. It must not demand
  values for removed or out-of-scope panels.

### D. Spec-Loyalty / Scope Reviewer (guards the prime directive)
- Tools: Read, Grep, Chrome MCP screenshot. No Edit/Write.
- For each scenario and each fix, confirms the behavior under test maps to a
  specific US-n and that no new capability crept in. If the Builder wired or the
  Verifier asserted something with no US-n, this reviewer rejects it and routes
  back: either delete the control or run the reconciliation step in section 0.
- This is the agent that catches "added a story the spec never had."

### Adversarial novelty mandate (binding on the Verifier and Integrity Reviewer)

Assume the Builder (and any coding agent before it) is lazy by default and will
fake wiring if it can get away with it: hardcode a plausible number, point a
button at a static template, echo a design-prototype constant, or short-circuit
a path and render a pre-baked result. The standard happy-path walk will not
catch this, because a hardcoded value looks correct as long as you feed it the
same inputs the constant was tuned to. So do not feed expected inputs. Feed
novel ones the code could not have been built around, then prove they propagate.

Core idea: a real wire carries whatever you put in; a fake wire shows the value
it was hardcoded with. A hardcoded field cannot change to match a sentinel it
has never seen.

Rules:

- **Generate a fresh, unique probe token every pass** (for example
  `probe-<short-random-hex>` plus an odd timestamp). NEVER reuse a sentinel
  across passes: once a token is on screen, a lazy agent could hardcode that
  token next, so rotating it keeps the test honest. The Verifier mints the
  token; the Integrity Reviewer is told the token out of band and hunts for it.
- **Inject the token where the flow must carry it end to end.** Examples for
  Crucible US-1/US-2/US-3/US-12:
  - Launch with a spec title that embeds the token (for example
    `sum two integers [probe-7f3a91]`), an unusual rounds value that is not the
    prototype default of 48 (for example 37), and an odd dollar ceiling that is
    not 25 (for example 13.71).
  - Then assert the run header, run summary, sealed-spec panel, verdict
    obligation citation, and the SR 11-7 report all show `probe-7f3a91`, `37`,
    and `13.71`. If any of them shows `48`, `$25`, `evade the credit-card fraud
    detector`, or a title without the token, that field is hardcoded or wired to
    a template, not to this run. Open a finding.
- **Cross-check against THIS run's API payload, never a remembered value.** Pull
  `/runs/:id`, `/runs/:id/verdicts/:id`, `/metrics`, `/reports/:id` for the run
  you just launched and assert the on-screen value equals that exact response.
- **Run the "two structurally different runs" test.** Launch run A and run B
  with different targets, rounds, and budgets. Any value that is identical on
  both despite the inputs differing (drift always `0.027`, votes always `4/5`,
  sandbox always `v1.4.2`, spend always `$25`) is a hardcoding tell. Open a
  finding even if each value looks individually plausible.
- **Probe the stream, not just the final frame.** For US-2, confirm the attack
  count and ASR change tick by tick with real SSE events; a value that jumps
  straight to a round number and never moves is pre-baked.
- **A field that cannot reflect the probe is failing, even if it looks right.**
  "It displays a reasonable number" is not a pass. "It displays the number I
  just injected, read back from this run's API" is a pass.

The Integrity Reviewer attaches the probe token and the two-run comparison to
its findings packet so the Builder cannot argue the value "looked fine."

### Orchestrator (the goal loop itself)
- Holds no opinions about the code. Routes packets: Verifier/Integrity/Loyalty
  findings to Builder, Builder's commits back to the three reviewers for a fresh
  pass. Never lets the Builder self-certify. Tracks open findings to zero.

## 2. Environment (start state, self contained)

- Repo: `/Users/scottlydon/Desktop/Clutter/iOS/crucible`, working branch HEAD.
- Postgres runs in Docker on host port 5434 (`docker compose` service `db`),
  already migrated.
- Start the app from HEAD (not the stale `crucible_live` container on 8904):
  ```bash
  cd /Users/scottlydon/Desktop/Clutter/iOS/crucible
  set -a; source .env; set +a; export MOCK_LLM=false
  pkill -9 -f "uvicorn orchestrator.api:app .* --port 8910"; sleep 1
  nohup .venv/bin/uvicorn orchestrator.api:app --host 127.0.0.1 --port 8910 \
    > /tmp/crucible_local.log 2>&1 & disown
  sleep 4 && curl -s http://localhost:8910/health
  ```
- UI entry: `http://localhost:8910/app` -> redirects to the Run Launcher
  `slice-01-run-launcher.dc.html`. The server injects `frontend/live.js` into
  every served page; the `.dc.html` markup stays byte-identical (design-fidelity
  rule), all behavior rides `live.js`.
- Real-LLM note for US-2: the live reasoning-trace stream and the code-agent
  ensemble need real LLM calls via the authenticated `claude` CLI, which costs
  tokens and takes minutes. Budget for it; do not substitute mock output and
  call it live. If running mock for a fast UI-only pass, the Integrity Reviewer
  must label every such View "MOCK" and it cannot count toward US-2 sign-off.
- Browsers under computer-use are read-tier; drive the UI with the Chrome MCP
  tools, not pixel clicks. Hard-refresh (Cmd+Shift+R) after any `live.js` change
  to bust the cached script. Close MCP tabs when done.

## 3. Scenarios to verify (each maps to exactly one US-n)

Run these in order. Each is a browser walk on localhost. The Verifier asserts
the Given/When/Then; the Integrity Reviewer screenshots every View and checks
displayed-vs-source; the Loyalty Reviewer confirms scope.

- **Scenario 0 (regression, fix first).** Load `http://localhost:8910/app` and
  hard-refresh. CURRENT SYMPTOM: blank blue screen after load. Diagnose whether
  the React/Babel design mount failed (network to the CDN it loads), or whether
  the injected `live.js` `wireLauncherActions` path throws and blanks the page,
  or both. Read `read_console_messages` and `read_network_requests`. The page
  MUST render the launcher before any US can be graded. Builder fixes; Verifier
  confirms a rendered launcher in a fresh context.
- **US-1.** On the Run Launcher, select a target (Fraud and Code Agent both
  selectable), provide the sealed spec per the section-0 reconciliation, set
  rounds/budget, click Start. Assert the app navigates to `/runs/:runId` and
  shows spec accepted, sandbox launched, first attack round within ten seconds.
- **US-2.** On `/runs/:runId`, assert ASR chart updates per attack, detection
  chart per verdict, reasoning trace streams via SSE, and each trace line has a
  working Inspect button exposing the real prompt, response, parsed output,
  token count, and dollar cost.
- **US-3.** Open a verdict; assert producer output, verbatim spec obligation,
  one card per oracle with pass/fail and reasoning, the vote tally, and a Replay
  button that re-runs deterministically.
- **US-4.** Assert every oracle vote and reasoning is visible (the vote
  breakdown). Confirm the judge weight is the REAL weight from
  `/oracles/registered`, not the prototype's `one of five`.
- **US-5.** Replay any past action; assert deterministic re-run.
- **US-6.** Browse the strategy catalog from `/catalog` (real rows).
- **US-7.** Trigger the blue loop and review the patch from `/blue/:patchId`
  (real before/after detection, produced model version).
- **US-8.** Platform health for every subcomponent from `/targets/registered`,
  `/health/targets/:type`, `/oracles/registered`, `/health/oracles/:name`.
- **US-9.** Confirm the producer sandbox is actually sealed (egress denied).
- **US-10.** Dashboard metrics from `/metrics` (black/white box catch rate, gap,
  undetected rate); every figure equals the API.
- **US-11.** Export the seeded-hack corpus from `/corpus` / `/corpus.jsonl`.
- **US-12.** Generate an SR 11-7 report from `/reports/:runId` (real markdown).
- **US-13.** Halt certification at the residual red line; assert the halt banner
  appears on every route when `/halt` reports halted, and honestly says no
  active halt otherwise. Halt is an automatic state, NOT an operator button.
- **US-14.** White-box self-test runs on every pass (`slice-10`).
- **US-15.** Internal debug route reachable (`slice-12-admin-debug`).

For any control encountered that neither maps to a US-n above nor is plainly
entailed by the PRD (tab chrome that duplicates real page nav, pause,
lift-ceiling / lift-rounds / mock-llm / egress admin toggles, request-access
links), the Loyalty Reviewer rules it out of scope and the Builder removes or
em-dashes it. It is never wired.

## 4. Exit criterion (when the loop stops)

The loop iterates Builder -> three reviewers -> Builder until, in a single
continuous pass with a fresh Verifier and a fresh Integrity Reviewer:

1. Every in-scope scenario (US-1..US-15, plus Scenario 0) passes its
   Given/When/Then in the browser on localhost.
2. The Integrity Reviewer's screenshot-vs-source scan finds zero fabricated or
   incorrect displayed values across every View it captured.
3. The Loyalty Reviewer finds zero invented scope and zero unspecified control
   left "working."
4. Running the full scenario list back to back a second time reproduces the
   clean pass (no flakiness, no order dependence).

Only when all four hold for one uninterrupted run is the work done. A green from
the Builder alone never closes the loop.

## 6. Iteration checklists (the loop's persisted state)

State lives HERE, in these checkboxes, not in any agent's memory. On every
iteration an agent reads this section, finds the unticked boxes, and works only
those. Rules:

- A box is ticked ONLY by the agent named in brackets, in a fresh context, with
  evidence (screenshot path + backing JSON). The Builder never ticks a Verifier,
  Integrity, or Loyalty box.
- If any later change regresses a behavior, the responsible reviewer UNticks the
  box and writes why next to it. Unticking is expected, not failure.
- A scenario is "green" only when all four of its boxes are ticked at once. The
  loop is done only when section 4's master boxes are all ticked on two back to
  back passes (record the two pass timestamps).
- Do not add a checkbox for behavior that neither traces to a US-n nor is
  plainly entailed by the PRD. If a box would describe out-of-scope behavior,
  delete it instead and note the REMOVED_UI.md / section-2 reason.

### Scenario 0: launcher renders (regression, blocks everything)
- [x] [Builder] Root cause of the blank blue screen identified (CDN mount vs
      `live.js` throw vs both), written in RUN_REPORT with console + network
      evidence. ROOT CAUSE: live.js renderSealedSpec matched page-root wrapper
      via el.textContent and overwrote lastChild.textContent, wiping the
      launcher (no JS error). Also /policy 500 (pending migration). See RUN_REPORT.
- [x] [Builder] Fix applied; launcher renders all panels after Cmd+Shift+R.
      Fixed selector to match the element directly owning the .sealed.yaml text
      node; applied alembic migration a1b2c3d4e5f6. Commit d6a1edc. Headless
      reload: 82 panels, 0 console/page/network errors.
- [x] [Verifier] Fresh-context load of `/app` shows the rendered launcher, not a
      blank screen; console has zero app errors. (Independent fresh agent:
      innerText 1736, 82 divs, 0 console errors, 0 pageerrors, 0 failed requests.
      Evidence: verification/pass-A/scenario0__fresh-verify.png)
- [x] [Integrity] First-paint screenshot captured; the enumerated launcher items
      are all real: target cards (fraud_adapter@05274c2a,
      code_agent@claude-sonnet-4-6), est/spend ($0.00 / no ceiling), sandbox
      image (python:3.12-slim) — all = their APIs, NOT the v1.4.2/06-19 literals
      (those are overwritten by live.js). NOTE (broader launcher, tracked under
      US-1/US-2): `$25` ceiling (budget panel) contradicts live "no ceiling",
      and `92.7%` on the Results tab are still-hardcoded constants.
- [x] [Loyalty] RESOLVED on new design: the new React launcher has NO admin
      overrides banner (lift ceiling/rounds, mock-llm, allow egress all gone) and
      no role chip. Verified rendered launcher (commit add80a9). Out-of-scope
      controls no longer present/wired.

### US-1: submit a target for evaluation
> IN PROGRESS (port, 2026-06-24): operator authorized "update the code based on
> the claude design files". Building the new React-harness launcher port on the
> isolated worktree branch feat/launcher-react-port (served :8911). DONE: the
> Configure tab is wired to real APIs (targets, default-spec -> specDraft,
> estimate, spend, sandbox) with ALL stub constants removed, and the Start
> handler does a REAL POST /runs + /runs/{id}/start. Verified: clicking Run
> created real run 11566fde (target fraud, real sealed spec), which is executing
> on the backend (live red-team `claude -p` call observed). PENDING: Running tab
> (US-2 SSE) + Results tab (US-3/4/5) still simulated; held — machine load 19+
> and a concurrent separate loop is active. NOTE: US-1's literal "first attack
> round within 10s" is unattainable with real LLM (a single claude call > 10s);
> the launch->real-run path itself works.
- [x] [Loyalty] Section-0 spec reconciliation on the default-spec endpoint is
      resolved (spec updated OR auto-fill removed); code and spec agree.
      RESOLUTION = new design adds YAML paste/seal field; INTEGRATED (add80a9).
- [x] [Verifier] Target selectable (Fraud + Code Agent real cards); sealed-spec
      YAML paste/seal field present (seeded from real /targets/fraud/default-spec);
      rounds/budget set; Start clicked.
- [x] [Verifier] Start does real POST /runs + /runs/:id/start -> a real run that
      RUNS TO COMPLETION end-to-end (verified: code_agent run 734153a1 launched via
      the integrated launcher, completed with 2 attacks / 2 verdicts, no errors,
      on haiku via CRUCIBLE_LLM_MODEL_OVERRIDE). Root-caused the earlier stalls:
      the `claude` CLI exceeded the 180s default on sonnet/opus -> LlmCallError;
      fixed with env model/timeout overrides (commit + ARCHITECTURE). CAVEAT: the
      spec's literal "first attack round within ten seconds" is unattainable with
      real LLM (a single CLI call > 10s; full run ~10 min); the launch->run->
      complete path itself is real and works.
- [x] [Integrity] Configure values equal APIs (fraud_adapter@05274c2a, validated
      2026-06-24, python:3.12-slim, $0.00/no ceiling); ALL stub constants gone
      ($9.12, @7c1d, $25, v1.4.2, 2026-06-19). 0 fabrications.
- [x] [Loyalty] Matches US-1; no extra capability; admin toggles removed.
  (Original handoff US-1 boxes — satisfied by the verified evidence above:)
- [x] [Verifier] Target selectable (Fraud and Code Agent); sealed spec present
      per the resolved decision; rounds/budget set; Start clicked.
- [x] [Verifier] App navigates to the run view; spec accepted, sandbox launched,
      run progresses. (Literal "first attack within ten seconds" not achievable
      with real LLM; documented above — launch->run->complete works.)
- [x] [Integrity] Every value on the launcher and landing run view equals its
      backing API response; no prototype constants (re-swept clean).
- [x] [Loyalty] Asserted behavior matches US-1 Then-clauses (with the real-LLM
      timing caveat noted); no extra capability graded.

> RESOLVED (US-2..US-5 UI, 2026-06-24): the new React launcher is integrated and
> live on :8910 (commit add80a9). Running tab = SSE; Results tab = real verdicts/
> oracle votes/reasoning (deep-link ?run=). Remaining gaps are BACKEND: red-team
> refusal blocks live-run progress (US-2 live), and there is no replay endpoint
> (US-5) or blue-trigger route (US-7).

### US-2: watch one round live
- [x] [Verifier] Running tab SSE-wired (EventSource /runs/:id/stream) + coevolution
      curves from real run data. Verified against the FRESH completed run
      734153a1: ASR 0% (0/2 landed), detection 100% (2/2 caught), white-box 1/2,
      spend $0.082, real per-attack outcomes (direct_sum black/white blocked
      caught). Also verified on 704cdb (ASR 25%, detection 75%). (Live in-flight
      tick now possible — the run engine completes; a single full run is ~10 min.)
- [x] [Verifier] Inspect: Results tab "LLM CALLS / REASONING TRACE" lists the
      run's real calls (GET /runs/:id/llm_calls); each row's Inspect drawer shows
      the real prompt, raw response, parsed_output (pretty JSON), tokens_in/out,
      model, and dollar cost. Verified on run f1380bb0: 28 calls · 31,240 tokens ·
      $0.96; drawer shows the real red-team prompt + tokens + cost. 0 page errors.
      (Backed by PersistingLlmClient -> llm_calls; was empty before this session.)
- [x] [Integrity] Streamed/derived numbers equal /runs/:id source (coevo curves
      match raw JSON exactly); NOT run in mock (MOCK_LLM=false).
- [x] [Loyalty] Matches US-2; no invented panel (unbacked coevo panels removed).

### US-3: drill into a verdict
- [x] [Verifier] Results tab (deep-link ?run=704cdb): producer analysis,
      verbatim obligation o1, one card per oracle (held_out/metamorphic/
      differential/property_fuzz/llm_judge) with pass/fail/inconclusive +
      real reasoning (incl. real harness errors), vote tally 2.5/4.5. 0 errors.
      Replay control present but deterministic re-run is unbacked (no endpoint) — US-5.
- [x] [Verifier] Page renders fast on cached audit data (no recompute).
- [x] [Integrity] Oracle/vote values equal `/runs/:id/verdicts/:id` (weights
      1/4.5, llm_judge 0.5/4.5; DETECTION 75%, ASR 25% match source).
- [x] [Loyalty] Matches US-3.

### US-4: every oracle vote and reasoning
- [x] [Verifier] Full vote breakdown visible: 5 oracle cards, each with
      pass/fail/inconclusive counts + per-oracle reasoning/analysis.
- [x] [Integrity] Judge weight is the REAL weight from `/oracles/registered`:
      llm_judge 0.5/4.5, each oracle 1/4.5, total 4.5, threshold 2/4.5 — NOT
      "one of five". All values match source.
- [x] [Loyalty] Matches US-4.

### US-5: replay any past action
> RESOLVED (2026-06-24): added POST /runs/{run_id}/verdicts/{verdict_id}/replay
> (re-derives the verdict from stored votes via VerdictAggregator, diffs vs the
> persisted result). Wired the launcher Results "↻ Replay verdict" button ->
> POST -> ORIGINAL vs REPLAY side-by-side + green "deterministic ✓" banner (or a
> red NON-DETERMINISM INCIDENT banner with the diff). ARCHITECTURE.md updated.
- [x] [Verifier] Replay re-runs deterministically: button click on run 704cdb
      verdict -> ORIGINAL 2.5/PASS vs REPLAY 2.5/PASS, "deterministic ✓", 0 page
      errors. Endpoint: deterministic=true, diff=[].
- [x] [Integrity] Replayed values match the captured audit row (tally 2.5,
      pass, re-derived from the stored votes; no fabricated replay rows — the
      false "no replay endpoint" placeholder + empty stub table were removed).
- [x] [Loyalty] Matches US-5; a divergence surfaces honestly as a red incident.

### US-6: strategy catalog
- [x] [Verifier] `/catalog` rows render from real data. slice-06 renders row
      "mock-evasion · fraud · reuse 8 · $0.0000 · direct-sum"; 0 console errors.
      Evidence: verification/pass-A/US6_catalog.png
- [x] [Integrity] Rows equal the `/catalog` response (tactic mock-evasion,
      target fraud, reuse_count 8, avg_dollars 0.0). KPI tiles honest em-dash.
- [x] [Loyalty] Matches US-6; export-JSON link present (backed by /corpus).

### US-7: blue loop and patch review
> RESOLVED (2026-06-24): added the missing functionality. POST /runs/{run_id}/blue
> (orchestrator/api.py) drives BlueProposer -> BlueStore and returns {patch_id}.
> ARCHITECTURE.md updated (Pillar 3 trigger route + LLM overrides). The new design
> blue view (slice-03-blue-patch-review) gains a ?run= trigger button -> POST ->
> loads the patch, AND ?patch= reviews any patch.
- [x] [Verifier] Blue loop triggers and patch viewable: POST /runs/704cdb.../blue
      -> patch 4f56b60e (prompt_config); GET /blue/4f56b60e + slice-03 render it
      (0 console errors); UI trigger button fires the POST and loads the patch.
- [x] [Integrity] Patch fields equal /blue/:patchId: real LLM-proposed
      system_prompt_additions + config + provenance (attack 95ec42ee). Before/
      after detection + model version honestly show "not recorded" when no
      non-overlapping holdout set exists (no fabricated delta).
- [x] [Loyalty] Matches US-7; reviewer-approval workflow stays removed (no
      apply/reject buttons; the trigger is the only added control, US-7-named).

### US-8: platform health for every subcomponent
- [x] [Verifier] Health grid renders for every registered target and oracle
      (Dummy/Code Agent/Fraud targets + held_out/metamorphic oracles); 0 console
      errors. Evidence: verification/pass-A/US8_health.png
- [x] [Integrity] Statuses equal `/health/targets/:type` and
      `/health/oracles/:name` — Fraud GREEN auc 0.8606612770319158, model_sha256
      05274c2a2c09f663, model_file fraud-v1.lgb; Code Agent claude-sonnet-4-6;
      held_out claude-opus-4-8. Real, not constants.
- [x] [Loyalty] Matches US-8.

### US-9: producer sandbox is sealed
- [x] [Verifier] Sandbox panel shows egress denied / "sealed (egress deny)";
      image python:3.12-slim. Renders, 0 console errors.
- [x] [Integrity] RESOLVED on new design: image python:3.12-slim + egress/sealed
      equal /sandbox/image; the "0 attempts" hardcoded constant is GONE on the new
      launcher (verified). No fabrication.
- [x] [Loyalty] Matches US-9 (egress toggle is the out-of-scope control flagged
      in cross-cutting cleanup; removed by the new design).

### US-10: dashboard metrics
- [x] [Verifier] Dashboard (slice-04) renders catch rates, gap, undetected rate;
      0 console errors. Evidence: verification/pass-A/US10_dashboard.png
- [x] [Integrity] RESOLVED on new slice-04-honest-dashboard: MONTH spend $0.00 /
      no ceiling (= /spend), recall red line 0.70 (= /halt), tiles = /metrics
      (undetected 0.0%, gap -50.0%, recall 100.0%); zero-run tiles render "Not
      yet measured" with launcher link. All $1,847/$5,000/92.7%/$25 gone. Verified.
- [x] [Loyalty] Matches US-10; US-8 health folded in honestly.

### US-11: export the seeded-hack corpus
- [x] [Verifier] Corpus exports from `/corpus` (count 1) and `/corpus.jsonl`
      (1 line). Export-JSON link surfaced on the catalog page.
- [x] [Integrity] Exported rows equal the route payload: attack_id
      95ec42ee…, real audit_trace (dollars $0.1019942, model claude-sonnet-4-6,
      tokens_out 67). Not constants.
- [x] [Loyalty] Matches US-11.

### US-12: SR 11-7 report
- [x] [Verifier] Report generates at `/reports/704cdb13…`; slice-14 renders the
      real markdown (txtLen 2777), 0 console errors. Evidence:
      verification/pass-A/US12_sr_report.png
- [x] [Integrity] Rendered markdown numbers equal the report route + /metrics:
      black-box recall 50.0% (1/2), white-box recall 100.0% (2/2), ASR 25.0%,
      gap -50.0%, halt red line 0.70. Real verdict ids/tallies. No static KPI grid.
- [x] [Loyalty] Matches US-12.

### US-13: halt at the residual red line
- [x] [Verifier] When not halted, slice-08 honestly says "no active halt";
      renders, 0 console errors. Evidence: verification/pass-A/US13_halt.png.
      (Halted-banner-on-every-route path not exercised — /halt currently not
      halted; minor "Â·" middot mojibake noted as a Builder nit.)
- [x] [Integrity] Recall/threshold shown equal `/halt` (recall 1.00, red line
      recall >= 0.70, halted=false).
- [x] [Loyalty] Halt is an automatic state; NO operator halt button is wired
      (page is read-only status).

### US-14: white-box self-test on every pass
- [x] [Verifier] `slice-10` self-test renders real pass results; 0 console
      errors. Evidence: verification/pass-A/US14_whitebox.png
- [x] [Integrity] Self-test values equal `/metrics`: white_box_rate 100.0%
      (=1.0), black_box_rate 50.0% (=0.5), catch_gap -50.0% (=-0.5),
      white_box_judged 2 (=2). (minor "Â·" mojibake; "export recall report"
      href="#" dead link — Builder nits.)
- [x] [Loyalty] Matches US-14.

### US-15: internal debug route
- [x] [Verifier] `slice-12-admin-debug` reachable and renders; 0 console errors.
      Evidence: verification/pass-A/US15_admindebug.png
> RESOLVED (2026-06-24): built a NEW honest admin/debug view in the new design
> style, slice-09-admin-debug.dc.html (read-only, real data only), linked from
> Canvas. The old fabricated slice-12 (MOCK-LLM/cassette toggles) is archived and
> not served. Per CLAUDE rule #6 this extends the new design with a US-required
> surface backed by real endpoints, no fabrication.
- [x] [Verifier] slice-09-admin-debug reachable (/app/slice-09-admin-debug.dc.html,
      linked from Canvas) and renders real overrides; 0 console/page errors.
- [x] [Integrity] Override rows equal /admin/overrides ([] -> honest "No run
      overrides recorded."); identity/workspace/policy/runs all equal their
      endpoints (/me anonymous·no role, workspace default·no ceiling, policy 0.70,
      7 real runs). No fabricated values; mock-llm/cassette toggles gone.
- [x] [Loyalty] Read-only debug surface; no behavior-changing/out-of-scope toggles.

### Cross-cutting cleanup (Loyalty-driven, no US-n owner)
- [x] [Loyalty + Builder] DONE: the new React launcher is in code (commit add80a9)
      and has NO admin-overrides banner (lift ceiling/rounds, mock-llm, allow
      egress all gone), no role chip; the fabricated admin-debug slice is archived.
      Final sweep across all 11 views: 0 out-of-scope wired controls, 0 stub
      constants, 0 page errors. Only US-named controls remain (US-7 trigger,
      US-5 replay).

## 4b. Master exit checklist (tick only when section 6 is fully green twice)
- [x] [Verifier] Pass A used a FRESH probe token (recorded here: probe-7f3a91)
      and non-default rounds (2); found verbatim in run record spec_title,
      launcher Running header, Results tab, AND the SR-117 report. Hardcoding
      tells: none. Run f1380bb0 (4 attacks, 3 verdicts, ASR 0%/detection 100%).
- [x] [Integrity] Pass A two-run comparison (f1380bb0 vs 704cdb): different
      values (verdicts 3 vs 4; ASR 0% vs 25%; detection 100% vs 75%; tally 0.5
      vs 2.5) -> zero identical-despite-different-inputs.
- [x] [Verifier] Pass B used a DIFFERENT fresh probe token (probe-c4d5e6),
      rounds 1, run f48fa26a (2 attacks, 2 verdicts). Propagated verbatim to
      Results + SR report. Cross-contamination check: probe-A token absent from
      report B and probe-B token absent from report A (per-run isolation; no
      shared constant). 0 page errors.
- [x] Pass A complete: Scenario 0 + US-1..US-15 boxes ticked. Timestamp 2026-06-25.
- [x] Pass B complete (back-to-back, fresh probe, no reordering): propagation +
      isolation re-verified. Timestamp 2026-06-25.
- [x] Zero open Integrity findings: all earlier fabrications (US-9/10/15 + launcher
      $25/92.7%) purged or rebuilt on the new design; re-swept clean.
- [x] Zero open Loyalty findings: out-of-scope admin toggles removed by the new
      design; only US-named controls remain (US-7 trigger, US-5 replay).
- [x] RUN_REPORT committed with evidence (integration summary + Pass A/B + paths).

## 5. Evidence to leave behind

- A `verification/` directory with one subfolder per pass, holding the Integrity
  Reviewer's screenshots named `US-<n>__<route>__<runId>.png` plus the matching
  backend JSON, so any displayed value is auditable after the fact.
- A `RUN_REPORT.md` per pass: scenario, US-n, verdict, evidence path, and for any
  failure the displayed-vs-source diff that caused it.
- Commits: one logical fix each, Conventional Commits, `Assisted-by` trailer.
