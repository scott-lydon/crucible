# Claude Design brief, ready-to-paste

Paste the prompt below into <https://claude.ai/design> (Claude Design, the Anthropic Labs design tool; not Claude Sonnet generating HyperText Markup Language (HTML)). Hit Generate. Export the bundle when it is finished and copy the bundle verbatim into `_design_bundle/` per the global `~/.claude/CLAUDE.md` "CLAUDE DESIGN FIDELITY" hard rule.

Do not paraphrase the prompt before pasting. Do not strip the route list to "save tokens." Claude Design needs the whole spec to keep the dashboard internally consistent across screens.

---

## Prompt to paste

Build the operator dashboard for Crucible, an adversarial security platform that attacks an artificial intelligence (AI) system, verifies its work with checks the producer cannot see, hardens the producer in a closed loop, and measures its own catch rate against an adversary that already knows the verification scheme.

The full architecture lives at `https://github.com/scott-lydon/crucible`. The product is open source, target-agnostic, and pitched at three customer segments: a bank's model risk officer subject to United States Federal Reserve Supervisory Letter 11-7 (SR 11-7); a code-generation agent vendor whose buyers ask "does this agent reward-hack our tests"; and a public-sector AI procurement officer.

The dashboard ships as a React 18 single-page application built with Vite and Tailwind, using Recharts for plots and React Router 6 for routing. The architecture website already exists at `website/index.html` in a dark theme (`bg #0a0e1a`, panel `#1a2236`, accent `#6366f1`, text `#e2e8f0`, muted `#94a3b8`). Match that palette so dashboard and architecture site share visual identity.

### Hard product rules the design must honor

1. **Transparency first.** Every component a user sees must let them drill into its inner workings: every large language model (LLM) call shows its prompt, raw response, parsed output, tokens, and dollars; every oracle vote shows the spec obligation it checked and its reasoning verbatim; every sandbox execution shows its standard output and standard error; every persisted action carries a Replay button. Hide only what is a real security risk (Application Programming Interface keys, database credentials, sandbox tokens).
2. **No fake values in any chart, tile, or report.** When a metric has not been measured yet, the tile renders the literal text "Not yet measured" with a link to the Run Launcher. Never a "0.0" sample value.
3. **Halt-certification banner** lives above every route as a global red bar when the white-box self-test recall is below threshold.
4. **"One vote" labeling.** The LLM judge oracle is rendered with smaller weight than the four independent oracles and carries a tooltip explaining why.

### Routes (ten screens to design)

For each route, design (a) the page layout, (b) one happy-state mock, (c) one empty-state mock, (d) one error-state mock.

1. **`/` (Run Launcher).** Pick a target adapter (Fraud, Code Agent, Research Agent disabled), paste a sealed specification in Yet Another Markup Language (YAML), set an attack budget (rounds and dollars), click Start. After Start, navigate to `/runs/:runId`.
2. **`/runs/:runId` (Live Run View).** Three vertical panes side by side:
   - Left: attack-success-rate (ASR) chart and detection-rate chart, both updating live via Server-Sent Events (SSE).
   - Center: red agent reasoning trace, streaming tokens, every line carries an Inspect button.
   - Right: oracle votes scrolling as verdicts land, each tagged with the oracle name and pass-or-fail.
   - Top: run header with target name, budget remaining, dollars spent, current round.
   - Bottom: a "Skip to white-box pass" button (advanced operators).
3. **`/runs/:runId/verdicts/:verdictId` (Verdict Detail).** Single page showing (a) the producer's output, (b) the sealed-spec obligation cited verbatim, (c) five cards in order: Held-Out Tests, Metamorphic Relations, Differential Cross-Family, Property-Based Fuzz, LLM Judge ("one vote"). Each card has obligation, observation, reasoning, pass-or-fail. (d) Aggregator's vote tally. (e) Replay button.
4. **`/catalog` (Strategy Catalog).** Sortable table of red-team tactics: name, target-type filter, first-discovered run, reuse count, average dollars to succeed. Row click opens a drawer with the prompt fragment, the discovery audit trace, and a "Run This Tactic Against a Different Target" button.
5. **`/metrics` (Honest Dashboard).** Five large tiles in a 2-row grid: undetected-hack rate; validation-versus-held-out gap (the headline number, larger than the others); recall on the seeded corpus; dollars per caught hack; human-minutes per thousand outputs. Below: black-box catch rate and white-box catch rate side by side, with the gap as its own tile. Every tile shows the count of contributing runs and the timestamp of the latest run.
6. **`/blue/:patchId` (Blue Patch Diff).** Three sections: proposed feature additions (diff view), proposed adversarial training samples (table with provenance link to the catalog entries that motivated each), held-out validation results (before / after detection rates side by side). "Apply Patch" button at bottom, disabled until validation passes.
7. **`/health` (Subcomponent Health).** Hierarchical view: pillar (Targets-and-Oracles, Red, Blue, Measure, Orchestrator, Shared), then module, then subcomponent. Each leaf row shows status (green and timestamp, amber with last-known-good plus current error, or red and current error), and carries a "Run Self-Test Now" button. The Producer Sandbox card has a special "Run Seal Probe" button per spec User Story 9.
8. **`/corpus` (Seeded Hack Corpus).** Table of successful attacks with download button (Java Script Object Notation Lines (JSONL) export). Filter chips by target-type and tactic.
9. **`/reports/:runId` (SR 11-7 Model Risk Report).** Six sections rendered from the run's data: purpose, model description, developmental evidence, ongoing monitoring, limitations, governance. Every numeric field is a clickable link that jumps to the source row identifier. "Download Markdown" and "Download Portable Document Format" buttons.
10. **`/admin/debug` (Internal Debug Route).** Three panes: (a) past-run picker with "Resume at round N", (b) Mock-LLM mode toggle (when on, a yellow banner appears on every route), (c) audit-row replayer (paste a row identifier, see the original and the replay side by side with a diff).

### Cross-cutting components (appear on every route)

- **Halt-certification banner.** Global red bar at the top whenever verifier recall on the white-box self-test is below the configured red line.
- **Cost meter.** Top-right corner. Two numbers: per-run dollars and cumulative session dollars.
- **Live connection indicator.** Top-right corner. Green dot when SSE is connected; amber while reconnecting; red when offline.
- **Mock-LLM mode banner.** Top of page, yellow, only when the debug route toggles mock mode on.

### Components to standardize across screens

- **InspectButton.** Small magnifying-glass icon that opens a side drawer showing the underlying LLM call (prompt, response, parsed output, tokens, dollars) or sandbox job (env applied, network rules, exit code, stdout, stderr). Used on every reasoning-trace line, every oracle card, every producer output panel.
- **ReplayButton.** Appears next to any action that has a captured seed. Click opens a side drawer showing original output and replay output diffed.
- **AuditTraceCard.** Per-oracle card showing obligation, observation, reasoning, pass-or-fail. Same shape on the verdict detail page and the live run view.
- **HealthBadge.** Green / amber / red dot plus timestamp plus optional error message. Used on `/health` leaves and inline anywhere a subcomponent is referenced.
- **CostChip.** Inline dollar amount with a tooltip showing pillar and run identifier. Used on every catalog row, every blue patch, every LLM call.
- **NotYetMeasuredTile.** Stand-in for any metric that has zero contributing runs. Renders the text and a "Run Launcher" link, never a numeric value.

### Visual style

- Dark theme matching `website/index.html`:
  - `bg #0a0e1a`
  - `panel #1a2236`
  - `accent #6366f1` (interactive primary)
  - `text #e2e8f0`
  - `muted #94a3b8`
  - `red #c0584f` (halt banner, errors)
  - `green #34d399` (health pass, detection recovered)
  - `amber #f59e0b` (warnings, mock-LLM mode)
- Typography: sans serif, with a monospace face for code, traces, prompts, and audit JavaScript Object Notation (JSON).
- Logos for technologies and oracles use the Simple Icons style already in `website/index.html` (an `<img>` tag from `cdn.simpleicons.org/<slug>/<hex>`).
- Charts use Recharts; line for ASR and detection over rounds, bar for verdict counts per oracle.

### What to deliver

A complete design bundle with one HTML file per route plus the standardized components in their own files, all using the palette above. Include both the happy state, the empty state, and the error state for each route. Use the route list as the bundle's directory shape so it copies cleanly into the live `dashboard/src/pages/` tree per the verbatim-copy rule.

End of prompt.

---

## What to do with the bundle Claude Design returns

1. Export the bundle from Claude Design.
2. Unzip into `_design_bundle/` at the repo root.
3. Copy the bundle into `dashboard/src/pages/` verbatim. Same filenames, same directory shape, same content. Do not "re-implement in idiomatic React"; the rule (per global `~/.claude/CLAUDE.md` "CLAUDE DESIGN FIDELITY") is verbatim copy.
4. Wire each route to the FastAPI endpoints listed in `plan.md` section 3.
5. Diff `_design_bundle/` against `dashboard/src/pages/` on every re-export so any drift is immediately visible.

## When the design must be re-exported

Re-run Claude Design (with this same prompt plus a delta paragraph) whenever:

- A new route is added to `spec.md`.
- A cross-cutting component is added or renamed.
- The palette changes in `website/index.html`.
- A user story changes the layout shape of an existing page.

Re-exports re-converge live to design, not the other way around. If the live tree has drifted from `_design_bundle/`, the live tree changes, not the design files.
