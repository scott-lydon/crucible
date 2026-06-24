# Claude Design brief, ready-to-paste

Paste the prompt below into <https://claude.ai/design> (Claude Design, the Anthropic Labs design tool; not Claude Sonnet generating HyperText Markup Language (HTML)). Hit Generate. Export the bundle when it is finished and copy it verbatim into `_design_bundle/`. The design files are canonical: copy them as-is, structure and all, rather than re-interpreting them.

Do not paraphrase the prompt before pasting. Do not strip the route list to "save tokens." Claude Design needs the whole spec to keep the dashboard internally consistent across screens.

---

## Prompt to paste

Build the operator dashboard for Crucible, an adversarial security platform that attacks an artificial intelligence (AI) system, verifies its work with checks the producer cannot see, hardens the producer in a closed loop, and measures its own catch rate against an adversary that already knows the verification scheme.

The full architecture lives at `https://github.com/scott-lydon/crucible`. The product is open source, target-agnostic, and pitched at three customer segments: a bank's model risk officer subject to United States Federal Reserve Supervisory Letter 11-7 (SR 11-7); a code-generation agent vendor whose buyers ask "does this agent reward-hack our tests"; and a public-sector AI procurement officer.

The dashboard ships as a React 18 single-page application built with Vite and Tailwind, using Recharts for plots and React Router 6 for routing. The palette is yours to choose; see the "Audience and palette decision" section below for the customer context to reason from. Whatever palette you pick will be back-applied to the architecture website so the two share visual identity.

### Claude Design stub labeling rule (mandatory)

Every value in a happy-state mock that is fabricated rather than literal product copy must be wrapped in the canonical Claude Design stub label. The wrapper is the only way the downstream strip and audit scripts (`scripts/strip_claude_design_stubs.py`, `scripts/audit_claude_design_stubs.py`) can tell a sample value from a real one once the bundle has been copied verbatim into `dashboard/src/pages/`. The full specification lives in `docs/CLAUDE_DESIGN_STUB_PROTOCOL.md`; the shape is summarized here for the prompt.

The exact textual shape:

```
__CLAUDE_DESIGN_STUB__[<key>|<kind>|<hint>]__<visibleValue>__/CLAUDE_DESIGN_STUB__
```

`<key>` is a dotted identifier (`metric.asr`, `runs.list[0].id`, `verdicts.held_out.passed`). `<kind>` is one of `number`, `string`, `percent`, `currency`, `count`, `timestamp`, `array`, `enum`. `<hint>` is free text describing the data source (`from /metrics`, `from SSE stream`, `from /runs/:runId/verdicts`). `<visibleValue>` is what the design renders at design time.

Example, the ASR tile in the metrics happy-state mock:

```html
<div class="metric-tile">
  <span class="label">Attack success rate</span>
  <span class="value">__CLAUDE_DESIGN_STUB__[metric.asr|percent|from /metrics]__92.3%__/CLAUDE_DESIGN_STUB__</span>
</div>
```

Empty-state and error-state mocks render real product copy ("Not yet measured", typed error text from `coding-practices.md` section 4), so they carry no wrappers. Only happy-state sample values are wrapped.

Cover every fabricated value, including chart data points. For a Recharts series, wrap each row:

```html
<script type="application/json" data-recharts="asrOverRounds">
[
  {"round": 1, "asr": __CLAUDE_DESIGN_STUB__[chart.asr_over_rounds[0].asr|number|from /runs/:runId/sse]__0.61__/CLAUDE_DESIGN_STUB__},
  {"round": 2, "asr": __CLAUDE_DESIGN_STUB__[chart.asr_over_rounds[1].asr|number|from /runs/:runId/sse]__0.49__/CLAUDE_DESIGN_STUB__}
]
</script>
```

Skipping the wrapper on a single value defeats the audit. The verbatim-copy rule already prohibits paraphrasing the bundle, so the wrappers ride into `dashboard/src/pages/` unchanged and the strip script handles them deterministically before any merge.

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
5. **`/metrics` (Dashboard).** Five large tiles in a 2-row grid: undetected-hack rate; validation-versus-held-out gap (the headline number, larger than the others); recall on the seeded corpus; dollars per caught hack; human-minutes per thousand outputs. Below: black-box catch rate and white-box catch rate side by side, with the gap as its own tile. Every tile shows the count of contributing runs and the timestamp of the latest run. No marketing label asserts that the values are real (real is the default expectation per `coding-practices.md` section 4); the callout is on the empty state, which renders the literal text "Not yet measured" with a link to the Run Launcher.
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

### Audience and palette decision (you pick the palette)

Pick a palette that resonates with all three customer segments at once. Do not default to "tech demo dark with neon accents"; reason about what the three audiences see every day and find a palette that earns trust from all three. Name the palette decision in a `_palette_notes.md` file in the design bundle, with the hex codes and the audience-by-audience rationale, so we can defend the choice in the architecture interview.

What the three audiences see daily:

1. **Bank model risk officer (Supervisory Letter 11-7 (SR 11-7) world).** Lives in Bloomberg Terminal, internal model governance portals, Excel risk dashboards. Visual context: dense data, restrained palettes, often dark backgrounds with amber or cyan data accents. Trust signals: typography hierarchy, gridded layouts, no playful illustration, no gradients, conservative iconography. Warning signals: marketing flourish, neon, anything that reads "consumer app."
2. **Code-generation agent vendor engineering lead.** Lives in GitHub Dark, Linear, Vercel, Sentry, Datadog. Visual context: dark theme is table stakes; strong accent colors used sparingly; sharp monospace; high information density without feeling crowded. Trust signals: a designer touched it (not bootstrap-grey), the data-to-chrome ratio is right, latency and cost are first-class. Warning signals: light theme as default (reads as marketing site, not tool); too much chrome.
3. **Public-sector artificial intelligence (AI) procurement officer.** Lives in National Institute of Standards and Technology (NIST) documentation, government Geographic Information System (GIS) tools, agency dashboards, often with strong accessibility requirements (Web Content Accessibility Guidelines (WCAG) AA contrast at minimum, AAA preferred). Visual context: institutional palettes, often United States flag-adjacent (deep navy, off-white, restrained red). Trust signals: contrast ratios are excellent, type is readable at smaller sizes, no decorative animation. Warning signals: low contrast, animated chrome, anything that prioritizes aesthetics over readability.

The intersection where all three feel at home: a dark or near-dark base (not pure black), one restrained primary accent that is neither neon nor pastel, two semantic accents (success and danger) chosen for WCAG AAA contrast on the base, an amber for warning that does not read alarming. Specifically avoid pure black backgrounds (banks read as terminal-from-the-90s), purple neon accents (banks and government read as "consumer AI hype"), and high-saturation gradients (procurement reads as marketing).

You are not obligated to follow that intersection literally; you are obligated to deliver a palette that defends itself to all three audiences and explain the decision in `_palette_notes.md`.

### Visual style

- Palette: your choice, per the section above.
- Typography: sans serif body face, monospace face for code, traces, prompts, audit JavaScript Object Notation (JSON), and dollar amounts. Type ramp must remain readable at 14 pixel base.
- Contrast: Web Content Accessibility Guidelines (WCAG) AA minimum across all text, AAA for body copy where possible.
- Logos for technologies and oracles use the Simple Icons style (an `<img>` tag from `cdn.simpleicons.org/<slug>/<hex>` where `<hex>` is the brand color). Confirm each chosen accent reads acceptably next to the brand-colored logos.
- Charts use Recharts; line for attack-success-rate and detection over rounds, bar for verdict counts per oracle. Pick chart colors from your palette, not Recharts defaults.
- Motion: no decorative animation. Data-driven transitions only (chart updates, state changes, drawer slides).

### What to deliver

A complete design bundle with one HTML file per route plus the standardized components in their own files, all using the palette you chose. Include the happy state, the empty state, and the error state for each route. Use the route list as the bundle's directory shape so it copies cleanly into the live `dashboard/src/pages/` tree per the verbatim-copy rule. Include `_palette_notes.md` at the bundle root naming the hex codes and the audience-by-audience rationale.

End of prompt.

---

## What to do with the bundle Claude Design returns

1. Export the bundle from Claude Design.
2. Unzip into `_design_bundle/` at the repo root.
3. Copy the bundle into `dashboard/src/pages/` verbatim. Same filenames, same directory shape, same content. Do not "re-implement in idiomatic React"; copy the structure verbatim too.
4. Wire each route to the FastAPI endpoints listed in `ARCHITECTURE.md` section 3.
5. Diff `_design_bundle/` against `dashboard/src/pages/` on every re-export so any drift is immediately visible.

## When the design must be re-exported

Re-run Claude Design (with this same prompt plus a delta paragraph) whenever:

- A new route is added to `acceptance-tests.md`.
- A cross-cutting component is added or renamed.
- A user story changes the layout shape of an existing page.
- The palette needs revisiting (audience feedback, accessibility audit finding).

Re-exports re-converge live to design, not the other way around. If the live tree has drifted from `_design_bundle/`, the live tree changes, not the design files. The architecture website at `website/index.html` re-syncs to whatever palette the latest export carries.
