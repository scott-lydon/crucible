# Crucible facade audit

Elements that **appear functional but are not**: hardcoded literals shown as if
they were live data, dead controls, fabricated sample data, and unreachable
pages. Verdicts are from reading source (`frontend/*.dc.html`, `orchestrator/`,
`modules/`), not from clicking the UI.

Confidence: "confirmed" = I verified the exact markup/code. "reported" = found by
the audit pass, line approximate (files are minified, line numbers unreliable).

---

## A. Fabricated data shown as real (no-fake-data violations)

These render invented values as if they were measurements. This is the most
serious class because a viewer cannot tell them from real output.

| # | Where | Evidence | Verdict |
|---|---|---|---|
| A1 | `slice-06-halt-certification.dc.html` | Four run-ids `r_8f3a`, `r_8f3b`, `r_8f3c`, `r_8f3d` rendered as links in the certification ledger | **confirmed fake.** Hardcoded sample ids, not from any run. The page makes only 1 backend call, so the surrounding recall/threshold numbers are almost certainly hardcoded too. |

## B. Dead controls (look clickable / editable, do nothing)

| # | Where | Evidence | Verdict |
|---|---|---|---|
| B1 | `Run Launcher.dc.html` spec panel | `start()` uses `const specObj = ds.spec` and the comment "No client-side YAML parser is bundled, so an edited draft falls back to the canonical object" | **confirmed.** The "author mode" YAML textarea accepts typing but edits are discarded; every run uses the canned default spec. You cannot change the task from the UI. |
| B2 | `Run Launcher.dc.html` + `slice-01-strategy-catalog.dc.html` | `budget: { max_attempts: ..., max_dollars: 25 }` (two files) | **confirmed.** Dollar ceiling is a hardcoded literal sent to the backend, never operator-configurable. |
| B3 | `slice-01`, `slice-02`, `slice-04`, `slice-06` | 12 links tagged `data-stub="link:TBD"` (Runs / Audit / Health nav, "export recall report", the four halt run-id links) | **confirmed dead.** Rendered as live nav/export affordances, navigate nowhere. |
| B4 | `slice-04-honest-dashboard.dc.html` | Window selector chips (24h / 7d / 30d / 90d / all) with no `onClick` | **reported.** Look like a time-window toggle; page appears fixed to one window. Needs a direct confirm. |

## C. Hardcoded literals where live data should be (Run Launcher)

| # | Where | Evidence | Verdict |
|---|---|---|---|
| C1 | RUN SUMMARY "Oracles" row | `<span>4 + judge</span>` | **confirmed hardcoded.** Should derive from `GET /oracles/registered` (which returns the real 4 oracles + judge at 0.5 weight). The script even carries a comment "never the hardcoded '1/5'", yet the summary is a fixed string. |
| C2 | Estimate breakdown drawer | `avg $/round $0.19 (last 12 fraud runs)` | **confirmed hardcoded.** The real per-round average comes from `/estimate`; this footnote is a fixed value and a fixed "last 12 fraud runs" claim. |
| C3 | Estimate breakdown drawer | `oracle calls/round 5 (4 + judge)` | **reported hardcoded literal.** |
| C4 | Target picker header | `<span ...>✓ selected</span>` | **confirmed static.** Always reads "selected" regardless of state; redundant with the per-card checkmark. |
| C5 | Component state | `rounds: 48` | **confirmed magic literal.** Default round count is an arbitrary baked-in number, not sourced from config; traces to an old "12 / 48" design mockup annotation. |

## D. Reachability facade

| # | Where | Evidence | Verdict |
|---|---|---|---|
| D1 | All slice dashboards | `slice-01` (strategy catalog), `slice-02` (whitebox self-test), `slice-03` (blue patch review), `slice-04` (honest dashboard), `slice-06` (halt cert), `slice-08` (SR 11-7 report), `slice-09` (admin debug) are linked only from the `Canvas.dc.html` contact sheet, not from the main app nav | **confirmed.** In the normal operator flow (Run Launcher Configure / Running / Results), there is no navigation to these pages. They exist and render but the user cannot reach them through the product. |

## E. Architecture-doc inaccuracies (same family, in docs not UI)

| # | Where | Evidence | Verdict |
|---|---|---|---|
| E1 | website / SVG fraud-adapter label | "LightGBM swap AE / GMM DAGM" | **confirmed wrong.** Real fraud target is only LightGBM (`modules/targets/fraud/fraud_target.py`). No autoencoder/GMM/DAGMM anywhere in the codebase. |
| E2 | `ARCHITECTURE.md:104-111, 397-398`; `README.md:122,314` | Describes `modules/targets/research_agent/` as an existing stub adapter | **confirmed wrong.** That directory does not exist on disk. The real third registered target is `dummy`. `/targets/registered` returns `['dummy','code_agent','fraud']`. |

---

## NOT facades (honest placeholders, leave them)

These look like gaps but are the correct pattern: they refuse to fake a number
the system genuinely does not have. Do not "fix" by inventing values.

- CPU % / memory % rendered as em-dash (`cpuPct = EMD`) because the API does not
  expose them.
- Wall-clock elapsed rendered as em-dash, commented "not exposed by the API".
- "Not yet measured" for cost-per-undetected-hack and human-minutes-per-1k on the
  dashboard, and the `/metrics` null-rate behavior (US-10).

---

## Suggested fix order (highest user-trust impact first)

1. **A1** remove the fabricated `r_8f3*` run-ids and wire the halt-cert ledger to
   real runs, or mark the page clearly unbuilt. Fake data presented as real is the
   worst offender.
2. **B1** wire the spec YAML textarea (backend parse path) so the operator can
   actually define the task. Without this the product's core promise is inert.
3. **B3** resolve the 12 `link:TBD` dead links: wire them or remove them.
4. **C1, C2, C3** bind the oracle summary and estimate footnotes to the real
   endpoints they already have.
5. **B2** source `max_dollars` and **C5** `rounds` from backend config (single
   source of truth) instead of literals.
6. **D1** add real navigation to the slice dashboards, or fold them into the main
   flow.
7. **E1, E2** correct the architecture docs/diagrams to match the code.
