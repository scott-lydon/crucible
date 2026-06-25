# Demo-loop bug log (Bug-Watcher → Builder)

Findings the recording/loyalty passes surfaced. Each: id, US-n, evidence,
expected-vs-shown. Builder fixes on `feat/crucible-build`, commits separately,
then the affected scenario is re-recorded and re-checked.

## BUG-L1 — out-of-scope screens exposed on deploy — FIXED + DEPLOY-VERIFIED
- Lane: Loyalty (Stage D). US: n/a (out of scope).
- Shown: `slice-05-coevolution-curves.dc.html` and
  `slice-07-leaderboard-export.dc.html` returned 200 on the deploy and were
  linked from Canvas nav, with no backend (`/coevolution`, `/leaderboard` 404).
- Expected: no out-of-scope route/screen (REMOVED_UI.md C6/C10; not in US-1..15).
- Fix: commit 90aabcd removed both pages + unlinked the Canvas cards.
- Verified: deploy dep-d8uijd5aeets73948ta0 live; both pages → 404; Canvas has
  0 links to them; in-scope screens intact. Operator approved removal.

## BUG-L2 — slice-04 dashboard co-evolution panel still present — OPEN
- Lane: Loyalty / Integrity (Stage R US-10).
- Shown: slice-04 renders a "Red ↔ Blue co-evolution" panel (empty state
  "No co-evolution data"). REMOVED_UI.md (slice-04 row) sanctions removal of the
  co-evolution panel (no backend). It is an honest empty state (not fabricated
  data), so lower severity than a NO-FAKE bug, but it advertises an out-of-scope
  feature on the dashboard the demo records.
- Expected: panel removed (consistent with the operator's BUG-L1 decision to
  remove co-evolution), OR operator explicitly keeps it.
- Action: confirm against rendered US-10 evidence; route to Builder for removal.

## BUG-R1 — US-6 catalog missing row-click reveal — OPEN
- Lane: Bug-Watcher (Stage R US-6). Ref acceptance-tests.md L116-117.
- Shown: catalog renders the sortable table (tactic, payload inline, target,
  reuse, $/succeed, first run) correctly from /catalog. But there is NO
  row-click reveal of the discovery audit trace and NO "Run This Tactic Against
  a Different Target" button anywhere on the page (grep of the served page +
  rendered innerText both find neither).
- Expected (US-6 Then): "clicking a row reveals the prompt fragment, the
  discovery audit trace, and a 'Run This Tactic Against a Different Target'
  button." prompt_fragment IS shown inline; the audit-trace reveal and the
  run-this-tactic button are missing.
- Note: /catalog already carries `discovery_audit.steps`, so the trace reveal is
  data-feasible; the "Run This Tactic" button needs a launch path.
- US-6 recording box stays UNTICKED until the reveal exists, then re-record.

## BUG-R2 — slice-04 dashboard: unwired "Recent runs" + "Audit replays" placeholder panels — OPEN
- Lane: Bug-Watcher / Loyalty (Stage R US-10).
- Shown: dashboard renders a "Recent runs" panel ("No runs recorded yet") and an
  "Audit row replays" panel ("No audit-row replays recorded yet") even though
  /runs has 10 real runs. The dashboard's x-dc script fetches /metrics, /spend,
  /halt, /health, /targets/registered, /oracles/registered — NOT /runs — so these
  two panels are unwired empty placeholders.
- Expected: REMOVED_UI.md (slice-04 row) says the 60-cell run-history strip +
  audit-row-replay preview are out (real runs come from the /runs list, audit
  replay is slice-05). Remove both placeholder panels from slice-04 (same
  decision as BUG-L2's co-evolution panel), OR wire Recent runs to /runs.
- US-10's five metric tiles are correct + honest (undetected 0.0%, gap -14.3%,
  recall 100.0% vs 0.70 red line, cost/human-min "Not yet measured"); only the
  two trailing placeholder panels are the issue. Re-record US-10 after the fix.

## BUG-R3 — target selector is non-functional (Run Launcher) — OPEN, SEVERE
- Lane: Bug-Watcher (US-1). Found by the OPERATOR, missed by the demo because the
  recording filmed the static Configure tab + a pre-existing seeded run instead of
  DRIVING the real flow (select target -> seal -> Start -> watch a launched run).
  This is a reward-hack on the recording side and is being corrected.
- Shown: the "Code Agent" target box (Run Launcher.dc.html line ~138) has
  cursor:pointer + a hover style but NO onClick handler. The Configure tab's only
  onClick handlers are openInspect, sealSpec, unsealSpec, openEstimate, start —
  none selects a target. `selectedTarget: 'fraud'` (line ~931) is the initial
  state and is NEVER changed by any setState. So clicking Code Agent does nothing;
  the run is permanently locked to the fraud target.
- Expected (US-1): "select a target (Shape 1 fraud OR Shape 2 code_agent) ... click
  Start ... navigates to /runs/:runId ... first round within ten seconds." The UI
  must let the operator actually choose code_agent (and fraud), reflect the
  selection (✓ + load that target's default-spec), and launch.
- Fix: wire onClick on BOTH target boxes to set selectedTarget (fraud|code_agent),
  move the ✓ / selected styling to the chosen one, and reload the sealed-spec draft
  from that target's /targets/<type>/default-spec. Builder, smallest change.
- CORRECTIVE ACTION: after the fix, DRIVE the real end-to-end flow on camera —
  click code_agent, confirm it selects, seal the spec, click Start, watch a real
  run launch and its first round — and re-record US-1..US-5 against THAT launched
  run (not a seeded one). Until then US-1..US-5 are un-ticked.

## BUG-R4 — run latency: a round takes ~8-15 min, not the US-1 "<10s first round" — OPEN
- Lane: Bug-Watcher (US-1, perf). Found by DRIVING the real flow (the corrective
  action after BUG-R3). A code_agent run launched via the fixed UI reaches its
  first finalized attack/verdict only after ~8-15 minutes, not "first round within
  ten seconds" (acceptance-tests.md US-1).
- Root cause: each round fires many SEQUENTIAL `claude` CLI calls (red proposes,
  target attempts, 5 oracles judge, blue), and every call spawns a fresh `claude`
  subprocess (auth + cold start overhead per call). CRUCIBLE_LLM_MODEL_OVERRIDE=haiku
  forces the model but does not parallelize or reduce call count, so runs stay slow.
- Impact on the DEMO: a run cannot be shown completing "live" in a short clip. The
  honest demo shows the REAL launch (US-1, driven on camera) and then the REAL
  results of that run after it completes (US-2..US-5), not pre-seeded data.
- Possible fixes (operator decision): parallelize the 5 oracle calls; reuse a warm
  CLI/SDK connection instead of a subprocess per call; or accept ~10-min runs and
  demo launch + completed-results. Not fixing blindly — surfaced for the operator.

## Findings from driving the real flow + fresh review (2026-06-25, after the reward-hack reset)

### BUG-R4 — run latency (oracle scoring) — FIXED (commit 9f2bd81)
Oracles scored sequentially; now concurrent (asyncio.gather), semantics/order preserved, tests pass.

### BUG-R5 — Pause/Halt buttons are UI-only (Running tab) — OPEN (scope decision)
BuilderTarget: pause/halt only flip client state (this.state.paused / runDone), NO backend POST. Clicking Halt does not stop the server run. NOTE US-13 says halt is AUTOMATIC with "no operator halt button" — so these buttons may be OUT OF SCOPE and should be REMOVED (like other out-of-scope controls), not wired. Operator decision: remove vs wire.

### BUG-R6 — sealed-spec read-only preview pane is static YAML — OPEN (minor)
BuilderTarget: the read-only sealed preview (Run Launcher ~lines 187-194) shows hardcoded obligation strings, not the selected target's real obligations. The EDITABLE draft textarea IS real/dynamic (from /targets/<type>/default-spec). Low severity unless the demo zooms the preview. Fix: bind the preview to real obligations, or accept.

### BUG-R7 — run latency: generate-all-attacks-upfront — OPEN (the 0/50 UX)
_red_pass calls red.search() which generates ALL attacks before driving any, so the UI sits at "attack 0/N" through the whole generation phase. Fix: stream/yield attacks so attempt 1 starts as soon as the first is generated (has catalog-adaptation correctness implications — separate careful ticket).

### BUG-R8 — run latency: ~9s/call CLI subprocess overhead — being addressed (CLI/API toggle)
Each `claude` CLI call pays ~9s subprocess+auth overhead on top of generation (~10-16s tiny, ~30-45s for the run's big prompts). Mitigation: UI toggle to run via the Anthropic API (BuilderToggle). Also: launcher default rounds=48 (line 914) makes every run ~96 attacks — drop to a small default (D).

### CAPTURE-DEFECT US-8 (not an app bug) — OPEN
demo capture probed /health/targets/fraud_adapter (404) instead of /health/targets/fraud; api.json contradicts the (correct) on-screen fraud-green badge. Live app is right (GET /health/targets/fraud -> green, AUC 0.8607, sha 05274c2a). Fix the capture apiRoutes token fraud_adapter->fraud + re-capture US-8.

## Resolutions (2026-06-25, continued)

### BUG-R3 — target selector "Clicking Code Agent does nothing" — VERIFIED FIXED
Driven end-to-end through the real UI with demo/flow_drive.mjs (headless Playwright,
DOM-level assertions, NOT static screens). 5/5 assertions PASS, 0 console errors:
1. Fraud is the default selection (✓ chip on Fraud card).
2. Clicking "Code Agent" moves the ✓ selected indicator to the Code Agent card.
3. Seal spec enables the Run-evaluation (Start) button.
4. Run evaluation creates a NEW run with target=code_agent (correct target propagated —
   if the click did nothing the run would default to fraud).
5. UI navigates to the Running view.
Video: demo/clips/flow-drive-code_agent.webm. This is the honest US-1 material.

### BUG-R5 — Halt vs Pause — RESOLVED (halt is now informational, not a launch gate)
Diagnosis (figure-out-what-happened): global white-box recall = 6/45 = 0.133, which
auto-halts certification (threshold 0.70). Per-run breakdown proved the halt is NOT
corruption: all 5 code_agent runs are at recall 1.00; the entire halt is driven by ONE
run, the operator's fraud run 26bac723, which ran on REAL models (sonnet/opus, no
override) and legitimately caught 0/39 white-box attacks — the true, expected result
that an informed attacker beats a static fraud classifier. The only actual corruption
was my 4 haiku-override runs (already deleted). 26bac723 is real data and is KEPT.
The halt is mathematically stuck (would need ~85 more caught white-box attacks to clear),
so it cannot recover while the real fraud finding exists, and deleting real data to
un-stick it would be a reward-hack. Per the operator's lean ("remove halt, keep pause"),
removed the create_run 409 launch-gate (orchestrator/api.py): a failing verifier is
exactly when you need to run MORE evaluations, so it must not freeze the platform. The
/halt banner + white-box recall metric stay (the SR 11-7 finding remains visible).
Verified: POST /runs returns 201 while /halt still reports halted=true. Pause stays as
the manual in-run control.

### Launcher rounds default — DONE
Run Launcher.dc.html rounds default is now 3 (line 907), down from 48 — every demo run
is ~6 attacks instead of ~96, so runs complete quickly on camera.
