# Crucible verification RUN_REPORT

Loop driven per `GOAL_LOOP_HANDOFF.md`. State of record is the section-6
checklist in the handoff. This report holds the per-scenario evidence the
checklist boxes cite.

Environment: app from HEAD on `http://localhost:8910`, real DB (Postgres on
5434), `MOCK_LLM=false`. UI driven headlessly via Playwright (Chromium) because
the in-browser MCP extension lacks host permission for `localhost:8910`; the
scripts live under `scratchpad/` and capture console, page errors, failed
requests, and the rendered DOM/screenshot for each View. Backend values are
pulled with `curl` from the same running process and compared to what renders.

---

## Scenario 0 — launcher renders (regression, blocks everything)

**Symptom (reproduced):** `http://localhost:8910/app` painted a blank
`#0E141B` screen showing only `spec.fraud.sealed.yaml · 6 lines`.
Evidence: `verification/pass-A/scenario0__app__BEFORE-blank.png`.

**Root cause (diagnosed, not the obvious one):** NOT a CDN/React mount failure
and NOT an uncaught `live.js` throw. `support.js` rendered the full launcher
correctly (host DOM = 34,688 chars at t≈488ms), then `live.js`'s
`renderSealedSpec()` silently wiped it (host → 33 chars by t≈615ms) with no JS
error logged.

The offending selector:

```js
// frontend/live.js (before)
var header = Array.prototype.find.call(
  document.querySelectorAll("div,span"),
  function (el) { return /\.sealed\.yaml/.test(el.textContent || "") && el.children.length <= 1; }
);
header.lastChild.textContent = " spec." + targetType + ".sealed.yaml · " + n + " lines";
```

`el.textContent` includes descendant text, so in document order the FIRST match
is the page-root wrapper (a `<div>` with `children.length === 1` whose single
child holds the entire launcher). Setting `header.lastChild.textContent` then
replaced the whole 34,688-char launcher subtree with the filename string.

Verified the mis-match directly: the matched element had `textLen 4158`,
`children 1`, `lastChild` an element with `innerHTML` length 34,688 — i.e. the
whole page.

**Fix (`frontend/live.js`):** match the element that DIRECTLY owns the
`.sealed.yaml` text in a child text node (the filename header row, sibling of
the yaml icon), never an ancestor:

```js
var header = Array.prototype.find.call(
  document.querySelectorAll("div,span"),
  function (el) {
    return Array.prototype.some.call(el.childNodes, function (n) {
      return n.nodeType === 3 && /\.sealed\.yaml/.test(n.nodeValue || "");
    });
  }
);
```

**Second defect found while clearing the console:** `GET /policy` returned 500
(`relation "workspace_policy" does not exist`). `workspace_policy` is a real
modeled table (`shared/persistence/models.py:422`) with migration
`a1b2c3d4e5f6`; the DB was one revision behind (`ec4dc1906055`). This is a
missing-migration deploy gap, not out-of-scope. Fix: `alembic upgrade head`
applied `a1b2c3d4e5f6`; `/policy` now 200 with real data
(`halt_recall_threshold 0.70`, `operative_policy ...`).

**Deploy verification (Scenario 0):**
- Layers: frontend `live.js` (served verbatim, no build step) + DB migration.
- live.js served fresh: `curl .../app/live.js | grep "DIRECTLY owns"` → 1.
- Migration: `alembic current` → `a1b2c3d4e5f6 (head)`; `/policy` → 200.
- Behavior: headless reload of `/app` → host stays 33,041 chars (full
  launcher), `visibleDivs 82`, PAGE ERRORS 0, CONSOLE 0, FAILED REQUESTS 0.
- Screenshot: `verification/pass-A/scenario0__app__AFTER-rendered.png`.

Builder boxes 1 and 2 satisfied. Verifier / Integrity / Loyalty boxes pending a
fresh-context pass.

---

## Pass-A verification sweep (Builder/diagnostic walk, pre fresh-context sign-off)

Driven headlessly (Playwright Chromium) on `http://localhost:8910`, each view
rendered and every displayed value cross-checked against its backing API via
curl. Screenshots under `verification/pass-A/`.

### Current live-frontend reality (branch feat/crucible-build)

The live launcher is the OLD design (admin toggles, read-only spec, `data-live`
hooks). `slice-02-live-run-view`, `slice-03-verdict-detail`,
`slice-05-audit-row-replayer` are ~1.3 KB redirect stubs to the launcher; the
redirect DROPS the `?run=` query param. live.js wires: metrics, health, halt,
lists (runs/catalog/specs/overrides), policy, health-grid, blue-patch, report,
SSE, halt-banner, launcher. It does NOT wire verdict-drill, oracle-votes, or
replay, and the launcher "Running" tab stays "no run started" even with `?run=`.

### Per-scenario status

| US | View | Renders | Console | Data verdict |
|----|------|---------|---------|--------------|
| S0 | launcher | YES (fixed) | 0 err | Builder-fixed; fresh verify pending |
| US-1 | launcher Configure | YES | 0 err | BLOCKED: no YAML paste field (design decision pending) |
| US-2 | Running tab | launcher only, "no run started" | 0 err | NO working UI (not wired) |
| US-3 | verdict detail | redirect→launcher | 0 err | NO working UI (not wired) |
| US-4 | oracle votes | — | — | NO working UI (not wired) |
| US-5 | replay | redirect→launcher | 0 err | NO working UI (not wired) |
| US-6 | catalog (slice-06) | YES | 0 err | REAL: row mock-evasion·fraud·reuse 8·$0.0000; KPI tiles em-dash. PASS |
| US-7 | blue-patch (slice-07) | YES (empty) | 0 err | GAP: no /blue trigger or list route; zero patches exist |
| US-8 | health (slice-11) | YES | 0 err | REAL: fraud auc 0.8606…, model_sha256, claude models. PASS |
| US-9 | sandbox panel | YES | 0 err | sandbox.image=python:3.12-slim REAL; but "denied · 0 attempts" HARDCODED (line 454) |
| US-10 | dashboard (slice-04) | YES | 0 err | tiles REAL (undetected 0.0%, gap -50.0%, recall 100.0% = /metrics); FABRICATED: MONTH "$1,847/$5,000" (l.58) + "$1,847/87 hacks" (l.161), real spend $0.00; red line "0.90" vs /halt 0.70 |
| US-11 | /corpus + catalog export | YES | 0 err | REAL: 1 row, full audit_trace. PASS (data) |
| US-12 | sr-report (slice-14) | YES | 0 err | REAL markdown: bb 50.0%(1/2), wb 100.0%(2/2), ASR 25.0%, gap -50.0%, halt 0.70 — all match /metrics+/halt. PASS |
| US-13 | halt (slice-08) | YES | 0 err | REAL: recall 1.00, red line 0.70 = /halt. PASS (minor "Â·" mojibake) |
| US-14 | whitebox (slice-10) | YES | 0 err | data-live wired to metrics; "—" defaults. Likely PASS (minor mojibake; "export recall report" href="#") |
| US-15 | admin-debug (slice-12) | YES | 0 err | FABRICATED: "MOCK-LLM MODE·ACTIVE" (server is MOCK_LLM=false), "acme-fraud/2026-06-15·12,418 turns·4 producers·1 judge", dead "change set"/"cassette diff" href="#". Should equal /admin/overrides ([]) |

### Loyalty (out-of-scope controls present in OLD design, removed by new design)
- Launcher admin banner: lift $ ceiling, lift rounds cap, mock-llm, allow egress toggles.
- admin-debug: mock-llm enable/disable, cassette controls, cost-meter toggle.
- Dead links href="#": request access, change set, cassette diff, export recall report.
The zip-3 design REMOVES the admin banner toggles and adds the YAML paste/seal field.

### Integrity findings opened (Builder fixes needed on CURRENT design)
1. US-10 dashboard: `$1,847/$5,000` (l.58) and `$1,847/87 hacks` (l.161) hardcoded; must show real spend ($0.00) or em-dash. Untagged so live.js never overrides.
2. US-10 dashboard: recall red line shows `0.90`; /halt threshold is `0.70` — inconsistent.
3. US-9: `denied · 0 attempts` hardcoded; must reflect real sandbox status, not a constant.
4. US-15 admin-debug: entire panel fabricated (MOCK-LLM ACTIVE, cassette set) while server is real-LLM and /admin/overrides is empty.

### Blocking gaps for forward progress
- US-1/US-2/US-3/US-4/US-5 require the new consolidated launcher design (zip-3) which is NOT yet integrated into code in this tree. The current code has no working UI for watching a run, drilling a verdict, oracle votes, or replay.
- US-7 has no backend route to trigger the blue loop or list patches.

---

## Scenario 0 — fresh-context independent verification (separate agent)

A fresh agent (did not write the fix) confirmed via headless Chromium:
- VERIFIER PASS: launcher renders, innerText 1736, 82 divs, 0 console errors,
  0 pageerrors, 0 failed requests. Screenshot verification/pass-A/scenario0__fresh-verify.png
- INTEGRITY: enumerated launcher items all real & live-hydrated (target refs
  fraud_adapter@05274c2a, code_agent@claude-sonnet-4-6; sandbox python:3.12-slim;
  spend $0.00 / no ceiling; validated 2026-06-24). The v1.4.2 / 2026-06-19
  literals in raw HTML are overwritten by live.js. TWO additional fabrications
  still live on the launcher: `92.7%` (Results tab, lines 547/743, not hydrated)
  and `$25` ceiling (budget panel; contradicts live "no ceiling"; live.js even
  falls back to ceiling:25). Tracked under US-1 (budget) / US-2 (results).
- LOYALTY FAIL: six out-of-scope controls present & wired to client state —
  pause/halt, lift $ ceiling, lift rounds cap, mock-llm, allow egress,
  request-access. Removed by the new design's deleted ADMIN OVERRIDES banner.

### Section-6 tally after this turn
24 → ~33 boxes ticked. Green scenarios: Scenario 0 (Verifier+Integrity; Loyalty
FAIL pending launcher port), US-6, US-8, US-11, US-12, US-13, US-14. Integrity
FAILs recorded: US-9 ("0 attempts"), US-10 ($1,847 spend / 0.90 red line),
US-15 (fake MOCK-LLM/cassette). Blocked on new-design port: US-1..US-5. Blocked
on trigger surface: US-7.
