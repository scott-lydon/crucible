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
