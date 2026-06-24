# Crucible: remaining work checklist

Authoritative list of what is NOT actually proven end-to-end, written
2026-06-24 after an honest audit. Each `- [ ]` line is a single
machine-checkable check. When its VERIFY command passes in the current
session, flip `- [ ]` to `- [x]` IN THIS FILE and commit the flip in the
same commit that landed the work.

The goal loop reads this file at the start of every iteration. The doc is
the state, not the chat. Do not track progress in chat or memory; track it
here.

## Hard rules to obey while working any item below

These are STANDING RULES, not work items. They are never "done" and never
ignorable. Re-read them on every iteration. They are deliberately NOT
formatted as checkboxes because a ticked checkbox semantically means
"complete, skip on the next pass" and these must never be skipped.

> **R1 · NO STUB / MOCK / FAKE / REUSED DATA.** If a number cannot be
> measured from a real run, the route returns null and the UI renders
> em-dash. Applies to every commit, every response, every artifact.

> **R2 · DISCLOSE UP FRONT, UNPROMPTED**, any time output is scripted,
> cached, replayed, or partially simulated. State which LLM calls were
> real and which were `ScriptedLlmClient` BEFORE the headline number,
> every time. Waiting to be asked is itself a violation.

> **R3 · DESIGN-FIDELITY WIRING.** When wiring frontend stub markup, the
> ONLY structural change to a `.dc.html` page is adding
> `data-live="<key>"` attributes (single attribute, no markup change).
> React state initializers (`state = {...}` blocks inside `<script>`
> tags) MAY be replaced with empty defaults because those are data,
> not markup.

> **R4 · PER-SLICE RITUAL.** Every code change runs ruff, mypy --strict,
> scripts/check_module_imports.py, pytest, then a conventional commit
> with `Assisted-by: Claude` trailer, dual-push (origin = github +
> gitlab, same hash), trigger Render deploy via REST API, verify on the
> live URL.

> **R5 · INLINE LINKS.** Every chat reply that touches this work begins
> with a live-URL link and a pending-PR link.

## Deploy commands (used after every commit)

```bash
# Trigger Render deploy (autoDeploy via API-created service is unreliable)
KEY=$(grep '^RENDER_API_KEY=' /Users/scottlydon/Desktop/Clutter/iOS/crucible/.env | cut -d= -f2-)
curl -s -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"clearCache":"do_not_clear"}' \
  "https://api.render.com/v1/services/srv-d8trfn9o3t8c73bvp470/deploys"

# Verify the deploy is live and on the expected hash
curl -s https://crucible-zaag.onrender.com/health
```

---

## Tier A: end-to-end real-LLM proof of the three pillars

These are the items the user explicitly flagged. Each represents a claim
in `tasks.md` that is overstated because no test or script exercises the
pillar with real LLM calls inside the full loop.

### A1 — End-to-end real-LLM run script

- [x] **DONE-CRITERION** A committed script at `scripts/run_e2e_real_llms.py`
  drives one POST /runs against the fraud target on the deployed Crucible,
  with every LLM call going to real models: `RedSearchAgent` calls real
  Sonnet for black-box and real Opus for white-box, `LlmJudgeOracle` calls
  real Opus, `BlueProposer` calls real Sonnet. Writes its measured
  headline numbers to a committed `artifacts/e2e_run_summary.json` whose
  schema is `{"run_id", "rounds_completed", "black_box_catch_rate",
  "white_box_catch_rate", "catch_rate_gap", "undetected_attacks",
  "blue_patch_id", "v1_global_recall", "v2_global_recall", "recall_delta",
  "total_llm_dollars", "started_at", "finished_at"}`. The script discloses
  up front that every value is real-LLM measured.
- **FILE/PATH** `scripts/run_e2e_real_llms.py`,
  `artifacts/e2e_run_summary.json`
- **VERIFY**
  ```bash
  CRUCIBLE_RUN_LLM_TESTS=1 uv run python scripts/run_e2e_real_llms.py --target fraud --rounds 48 --budget 25
  test -s artifacts/e2e_run_summary.json && python3 -c "import json; d=json.load(open('artifacts/e2e_run_summary.json')); assert d['black_box_catch_rate'] is not None"
  ```

### A2 — Real-LLM run persisted in production database

- [x] **DONE-CRITERION** The same run from A1 also lands in the live Render
  Postgres so the dashboard reflects it. After the script completes,
  `GET https://crucible-zaag.onrender.com/runs` returns a row whose
  `target_type` is `fraud` and `status` is `complete`, and `GET /metrics`
  returns non-null `black_box_catch_rate.rate` and
  `white_box_catch_rate.rate`.
- **VERIFY**
  ```bash
  curl -s https://crucible-zaag.onrender.com/metrics | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['black_box_catch_rate']['rate'] is not None, d"
  curl -s https://crucible-zaag.onrender.com/runs | python3 -c "import sys,json; rs=json.load(sys.stdin); assert any(r['target_type']=='fraud' and r['status']=='complete' for r in rs), rs"
  ```

### A3 — Real-LLM blue cycle persists v2 and measurable recall delta

- [x] **DONE-CRITERION** After A1's script runs, a `blue_patches` row
  exists for the fraud target, a `model_versions` row points at the
  produced v2 artifact, and the artifact `artifacts/fraud-v2.lgb` is
  committed (replacing the test-temp-only behavior).
  `artifacts/e2e_run_summary.json` records `v1_global_recall` and
  `v2_global_recall` measured against ALL 492 real frauds in the Kaggle
  dataset.
- **VERIFY**
  ```bash
  test -s artifacts/fraud-v2.lgb
  python3 -c "import json; d=json.load(open('artifacts/e2e_run_summary.json')); assert d['v2_global_recall'] > d['v1_global_recall']"
  curl -s https://crucible-zaag.onrender.com/blue/$(python3 -c "import json; print(json.load(open('artifacts/e2e_run_summary.json'))['blue_patch_id'])") | head -c 200
  ```

### A4 — Retrainer versioning bug fixed

- [x] **DONE-CRITERION** `modules/blue/retrainer.py` writes the next
  artifact as `fraud-v{n+1}.lgb` where `n` is the highest existing version
  on disk. A regression test in `modules/blue/tests/test_blue.py` asserts
  that running the Retrainer with `fraud-v1.lgb` already present writes
  `fraud-v2.lgb`, not another `fraud-v1.lgb`. Test passes against
  `uv run pytest`.
- **FILE/PATH** `modules/blue/retrainer.py`,
  `modules/blue/tests/test_blue.py`
- **VERIFY**
  ```bash
  uv run pytest -q modules/blue/tests/test_blue.py::test_retrainer_bumps_version
  ```

---

## Tier B: scaffolding shipped, real-data evidence missing

These items light up automatically once A1 lands real data. Verify each
AFTER the A1 script has completed at least one real run.

### B1 — `/metrics` shows real black-box and white-box catch rates

- [x] **DONE-CRITERION** Both `rate` fields are non-null floats on the
  live service.
- **VERIFY**
  ```bash
  curl -s https://crucible-zaag.onrender.com/metrics | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['black_box_catch_rate']['rate'] is not None and d['white_box_catch_rate']['rate'] is not None"
  ```

### B2 — `/halt` is meaningful (threshold defensible against real recall)

- [x] **DONE-CRITERION** A test, gated by A1 having run, asserts that if
  the measured white-box recall is below `HALT_RECALL_THRESHOLD` then
  `GET /halt` returns `halted: true` and a subsequent `POST /runs` returns
  409.
- **FILE/PATH** `tests/integration/test_halt_against_real_run.py` (new)
- **VERIFY**
  ```bash
  uv run pytest -q tests/integration/test_halt_against_real_run.py
  ```

### B3 — `/corpus.jsonl` exports real undetected attacks

- [x] **DONE-CRITERION** After A1, `curl https://crucible-zaag.onrender.com/corpus.jsonl`
  returns at least one line whose `tactic` and `target_type` fields are
  real, not from a dummy run.
- **VERIFY**
  ```bash
  curl -s https://crucible-zaag.onrender.com/corpus.jsonl | head -1 | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); assert d['target_type'] == 'fraud'"
  ```

### B4 — `/reports/:runId` SR 11-7 report renders against real run

- [x] **DONE-CRITERION** Fetching the report for A1's run_id returns
  Markdown whose numbers link back to row routes that resolve to real
  verdict/attack rows.
- **VERIFY**
  ```bash
  RUN_ID=$(python3 -c "import json; print(json.load(open('artifacts/e2e_run_summary.json'))['run_id'])")
  curl -s "https://crucible-zaag.onrender.com/reports/$RUN_ID" | grep -q "Risk Report"
  ```

### B5 — Strategy catalog has real entries

- [x] **DONE-CRITERION** `GET /catalog` returns at least one entry whose
  `target_type` is `fraud` and whose `reuse_count` is from a real run.
- **VERIFY**
  ```bash
  curl -s https://crucible-zaag.onrender.com/catalog | python3 -c "import sys,json; d=json.load(sys.stdin); assert any(e['target_type']=='fraud' for e in d), d"
  ```

### B6 — Code-agent end-to-end recovery measured

- [ ] **DONE-CRITERION** Either A1 is extended to also exercise the
  code-agent target, OR a separate script `scripts/run_e2e_code_agent.py`
  produces `artifacts/code_agent_e2e_summary.json` with before/after
  pass-rate numbers from a real-LLM code-agent run. Same disclosure rules
  as A1.
- **VERIFY**
  ```bash
  test -s artifacts/code_agent_e2e_summary.json
  ```

---

## Tier C: frontend pages still stubbed

Stub counts captured 2026-06-24 after slice-21 ship. The done-criterion
for every page in this section is: zero hardcoded run IDs
(`r_[0-9a-f]{4}`), zero hardcoded dollar amounts (`$[0-9]+\.[0-9]+`),
zero hardcoded dates (`2026-XX-XX`), and every visible value is either
real from a backend route or rendered as em-dash.

### C1 — slice-01 drawer copy (15 residual stubs)

- [x] **DONE-CRITERION** Zero raw stubs in the Inspect, Estimate, Role
  drawers. Judge invocation row, role elevation since/expiry, prior-run
  table cells all read from real routes or render em-dash.
- **FILE/PATH** `frontend/slice-01-run-launcher.dc.html`
- **VERIFY**
  ```bash
  test $(grep -cE '\$[0-9]+\.[0-9]+|r_[0-9a-f]{4}|m\.chen|amount_sign_flip' frontend/slice-01-run-launcher.dc.html) -eq 0
  ```

### C2 — slice-04 honest dashboard (80 stubs, 1 hook)

- [x] **DONE-CRITERION** Same as C1, on this file.
- **FILE/PATH** `frontend/slice-04-honest-dashboard.dc.html`
- **VERIFY**
  ```bash
  test $(grep -cE '\$[0-9]+\.[0-9]+|r_[0-9a-f]{4}' frontend/slice-04-honest-dashboard.dc.html) -eq 0
  ```

### C3 — slice-06 strategy catalog (2 stubs)

- [x] **DONE-CRITERION** Zero raw stubs; `data-live-list="catalog"` host
  is present and live.js's existing `wireList("catalog", "/catalog", catalogRow)`
  populates it.
- **FILE/PATH** `frontend/slice-06-strategy-catalog.dc.html`
- **VERIFY**
  ```bash
  test $(grep -cE '\$[0-9]+\.[0-9]+|r_[0-9a-f]{4}' frontend/slice-06-strategy-catalog.dc.html) -eq 0 && grep -q 'data-live-list="catalog"' frontend/slice-06-strategy-catalog.dc.html
  ```

### C4 — slice-07 blue patch review (2 stubs)

- [x] **DONE-CRITERION** Zero raw stubs; the page reads its content from
  `/blue/{patch_id}` where `patch_id` comes from a URL parameter;
  null/absent patch renders `no patch selected`.
- **FILE/PATH** `frontend/slice-07-blue-patch-review.dc.html`
- **VERIFY**
  ```bash
  test $(grep -cE '\$[0-9]+\.[0-9]+|r_[0-9a-f]{4}' frontend/slice-07-blue-patch-review.dc.html) -eq 0
  ```

### C5 — slice-08 halt certification (7 stubs)

- [x] **DONE-CRITERION** Zero raw stubs; page reads `/halt`; if
  `halted: false` the page shows `no active halt`; if `true` it shows the
  real reason and the timestamp.
- **FILE/PATH** `frontend/slice-08-halt-certification.dc.html`
- **VERIFY**
  ```bash
  test $(grep -cE '\$[0-9]+\.[0-9]+|r_[0-9a-f]{4}' frontend/slice-08-halt-certification.dc.html) -eq 0
  ```

### C6 — slice-09 coevolution curves

- [x] **DONE-CRITERION** EITHER a backend `/coevolution` route is added
  (returns `{round, asr, detection}` series joined to real runs) AND the
  page renders the series, OR the page is removed from the dashboard and
  the link in slice-04 / slice-01 is deleted. `tasks.md` already lists
  this as a stretch goal; treat it as a deliberate decision.
- **FILE/PATH** `frontend/slice-09-coevolution-curves.dc.html`, optional
  new route in `orchestrator/api.py`.
- **VERIFY** if route added:
  ```bash
  curl -s https://crucible-zaag.onrender.com/coevolution | python3 -c "import sys,json; assert isinstance(json.load(sys.stdin), list)"
  ```
  if removed:
  ```bash
  test ! -e frontend/slice-09-coevolution-curves.dc.html
  ```

### C7 — slice-10 whitebox self-test (1 stub residual)

- [x] **DONE-CRITERION** Zero raw stubs; page reads `/metrics` plus
  `/oracles/registered` to render the disclosure scheme.
- **FILE/PATH** `frontend/slice-10-whitebox-selftest.dc.html`
- **VERIFY**
  ```bash
  test $(grep -cE '\$[0-9]+\.[0-9]+|r_[0-9a-f]{4}' frontend/slice-10-whitebox-selftest.dc.html) -eq 0
  ```

### C8 — slice-11 health (entirely static, 0 hooks)

- [x] **DONE-CRITERION** Each target's row reads from
  `/health/targets/{type}` and each oracle's row reads from
  `/health/oracles/{name}`. The page renders the real probe status, not
  static green dots.
- **FILE/PATH** `frontend/slice-11-health.dc.html`
- **VERIFY**
  ```bash
  grep -q 'data-live=' frontend/slice-11-health.dc.html
  ```

### C9 — slice-12 admin debug (3 stubs)

- [x] **DONE-CRITERION** Backend `/admin/overrides` route added; page
  reads it and renders an empty audit log when there are no overrides
  recorded. The toggles in the override bar become POSTs that persist to
  a `run_overrides` table.
- **FILE/PATH** `frontend/slice-12-admin-debug.dc.html`,
  `orchestrator/api.py`, new migration.
- **VERIFY**
  ```bash
  curl -s https://crucible-zaag.onrender.com/admin/overrides | python3 -c "import sys,json; assert isinstance(json.load(sys.stdin), list)"
  ```

### C10 — slice-13 leaderboard export (7 stubs)

- [x] **DONE-CRITERION** EITHER a `/leaderboard` route is added (top-N
  runs by catch rate or by recovered evasions) AND the page renders it,
  OR the page is removed.
- **FILE/PATH** `frontend/slice-13-leaderboard-export.dc.html`
- **VERIFY** if route added:
  ```bash
  curl -s https://crucible-zaag.onrender.com/leaderboard | python3 -c "import sys,json; assert isinstance(json.load(sys.stdin), list)"
  ```
  if removed:
  ```bash
  test ! -e frontend/slice-13-leaderboard-export.dc.html
  ```

### C11 — slice-14 SR 11-7 report (1 stub)

- [x] **DONE-CRITERION** The page renders the SR 11-7 report for a real
  run via `/reports/{runId}` when a `?run=<id>` URL parameter is present,
  and shows `no run selected` otherwise.
- **FILE/PATH** `frontend/slice-14-sr-117-report.dc.html`
- **VERIFY**
  ```bash
  test $(grep -cE '\$[0-9]+\.[0-9]+' frontend/slice-14-sr-117-report.dc.html) -eq 0
  ```

### C12 — slice-15 workspace policy (7 stubs)

- [x] **DONE-CRITERION** Backend `/policy` route added that returns the
  workspace's policy YAML from a `workspace_policy` table; page renders
  the real policy.
- **FILE/PATH** `frontend/slice-15-workspace-policy.dc.html`,
  `orchestrator/api.py`, new migration.
- **VERIFY**
  ```bash
  curl -s https://crucible-zaag.onrender.com/policy | head -c 50
  ```

### C13 — slice-16 spec history (2 stubs)

- [x] **DONE-CRITERION** Backend `/specs/history` route added that
  returns the versioned spec rows from the `specs` table; page renders
  the real list.
- **FILE/PATH** `frontend/slice-16-spec-history.dc.html`,
  `orchestrator/api.py`.
- **VERIFY**
  ```bash
  curl -s https://crucible-zaag.onrender.com/specs/history | python3 -c "import sys,json; assert isinstance(json.load(sys.stdin), list)"
  ```

---

## Tier D: operational items

### D1 — Render autoDeploy connected to GitHub webhook

- [ ] **DONE-CRITERION** A push to `feat/crucible-build` triggers a
  Render deploy automatically; no manual REST `POST /deploys` call is
  required. Confirm by pushing a docs-only commit and watching the deploy
  fire within 60 seconds.
- **VERIFY**
  ```bash
  H=$(git rev-parse HEAD)
  sleep 65
  KEY=$(grep '^RENDER_API_KEY=' /Users/scottlydon/Desktop/Clutter/iOS/crucible/.env | cut -d= -f2-)
  curl -s -H "Authorization: Bearer $KEY" "https://api.render.com/v1/services/srv-d8trfn9o3t8c73bvp470/deploys?limit=1" | python3 -c "import sys,json; ds=json.load(sys.stdin); assert ds[0]['deploy']['commit']['id'].startswith('$H'[:7]), ds[0]['deploy']['commit']['id']"
  ```

### D2 — CI runs the opt-in real-LLM and slow tests weekly

- [ ] **DONE-CRITERION** GitHub Actions workflow
  `.github/workflows/ci-llm-weekly.yml` runs `CRUCIBLE_RUN_LLM_TESTS=1`
  and `CRUCIBLE_RUN_SLOW_TESTS=1` on a cron schedule, fails the job loud
  on any regression, and uploads the run log as an artifact.
- **VERIFY**
  ```bash
  test -e .github/workflows/ci-llm-weekly.yml && gh workflow run ci-llm-weekly.yml -R scott-lydon/crucible
  ```

### D3 — Vouch (QA-Adversary) run on this branch

- [x] **DONE-CRITERION** Invoke the `vouch` sub-agent against the current
  diff range, address any blocking findings, commit fixes if needed.
- **VERIFY** vouch report appears at `/tmp/vouch_report_<sha>.md`; no
  blocking findings, or fixes committed.

### D4 — Submit-gate verdict re-evaluated

- [x] **DONE-CRITERION** After A1 lands the headline number, re-read
  `~/.claude/skills/submit-gate/SKILL.md` and re-issue the verdict in
  chat honestly. If A1 fails the gate, list what specifically failed.
- **VERIFY** verdict in chat names every line of the gate's checklist.

---

## Stopping condition

Every Tier A, B, C, and D `- [ ]` above has flipped to `- [x]` and its
VERIFY command passes. At that point:

- `git status` is clean.
- HEAD pushed to GitHub and GitLab (same hash).
- Render deploy on that HEAD is live and `/health` returns 200.
- `artifacts/e2e_run_summary.json` exists with real-LLM numbers.
- `submit-gate` verdict is PASS with evidence.

Until then, every chat reply about this work includes the live URL, the
pending PR URL, and a one-line status of which Tier item is in progress.
