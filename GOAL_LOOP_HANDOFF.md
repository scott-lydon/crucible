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

- **Verify only behavior that traces to a US-n acceptance test.** If a control,
  number, panel, or page cannot be traced to a specific US-n, it is not a
  feature to make work. Do not assert it, do not wire it, do not grade it.
- **Never invent a user story.** If you find yourself adding a capability that
  no US-n names (operator pause button, admin override toggles, halt-as-action,
  multi-tenant, a spec compiler, mobile layout), STOP. Those are out of scope
  per `acceptance-tests.md` section 2 and `REMOVED_UI.md`.
- **The honest fix for an unspecified, non-functional control is removal or an
  em-dash placeholder, not a new backing route.** A dead button that no US
  requires gets deleted or disabled, never "made to work."
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

For any control encountered that maps to none of the above (tab chrome that
duplicates real page nav, pause, lift-ceiling / lift-rounds / mock-llm / egress
admin toggles, request-access links), the Loyalty Reviewer rules it out of
scope and the Builder removes or em-dashes it. It is never wired.

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

## 5. Evidence to leave behind

- A `verification/` directory with one subfolder per pass, holding the Integrity
  Reviewer's screenshots named `US-<n>__<route>__<runId>.png` plus the matching
  backend JSON, so any displayed value is auditable after the fact.
- A `RUN_REPORT.md` per pass: scenario, US-n, verdict, evidence path, and for any
  failure the displayed-vs-source diff that caused it.
- Commits: one logical fix each, Conventional Commits, `Assisted-by` trailer.
