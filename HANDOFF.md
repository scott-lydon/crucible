# Crucible handoff (2026-06-24)

Snapshot of the `REMAINING_WORK.md` push. This supersedes the earlier handoff.

## Coordinates

- **Repo:** `/Users/scottlydon/Desktop/Clutter/iOS/crucible`
- **Branch:** `feat/crucible-build` (dual-pushed: GitHub `scott-lydon/crucible` + GitLab `labs.gauntletai.com/scottlydon/crucible`, same hash)
- **Live:** https://crucible-zaag.onrender.com (Render service `srv-d8trfn9o3t8c73bvp470`, runs `MOCK_LLM=true`)
- **PR (do not merge):** https://github.com/scott-lydon/crucible/pull/3
- **State file:** `REMAINING_WORK.md` (the authoritative checklist; the doc is the state, not chat)
- **Removed UI log:** `REMOVED_UI.md` (out-of-PRD design sections taken out, with re-add conditions)

## Status: 26 of 27 done; only D2 open (blocked on a merge)

Every Tier A, all of Tier B (B1 to B6), all 13 Tier C, and D1/D3/D4 are checked
and verified. The lone open item, D2, is blocked on the PR reaching `main`.

### The headline (Tier A real-LLM proof)

One real-LLM end-to-end run drove the deployed fraud target with every LLM call
on real models (`scripts/run_e2e_real_llms.py`), run locally (authenticated
`claude` CLI on Claude Max) writing to the production Postgres. Result, committed
to `artifacts/e2e_run_summary.json` and verified live:

- run `a279028d`, 32 rounds, **$11.28** on Max, 64 calls (17 Sonnet, 47 Opus)
- the Sonnet/Opus red agent **evaded the detector on 31 of 32 attempts**, so
  black-box and white-box catch rate are a measured **0.00** (an honest result:
  the model has real blind spots an adaptive LLM adversary exploits)
- one blue round hardened on the missed frauds: **v1 global recall 0.898 to v2
  0.965** (delta +0.067) over all 492 Kaggle frauds; `artifacts/fraud-v2.lgb`
  committed
- certification **auto-halted** (white-box recall 0.0 below the 0.7 red line);
  `POST /runs` now returns 409 on the live service

Verified live: `/metrics` non-null, `/runs` has the complete fraud run,
`/corpus.jsonl` + `/catalog` hold 31 real undetected attacks, `/reports/{run}`
renders, `/blue/{patch}` resolves, `/halt` returns halted.

### The one architecture decision worth knowing

The proposal splits verification by domain: the four independent oracles verify
the **code** domain; a scored model (the fraud detector) is measured by its own
`query_target` score (attack-success-rate), not the code oracles. The loop used
to force every target through the code-oracle ensemble, which abstains on a
numeric artifact, so no fraud attack could ever be recorded as undetected and
the catch-rate collapsed to a structural 100%/0. Fixed with a target-agnostic
`Target.oracle_verified` property (True for code/dummy, False for the fraud
model); the loop, metrics, and halt rule read the domain-appropriate undetected
signal off `attacks.succeeded`. No bespoke fraud oracle was added (the model's
own score is the ground-truth signal the proposal prescribes). See commit
`fix(verify): a scored model's evasion is its own query_target miss`.

A second real bug the live run caught: `feature_row` crashed on a real proposal
that set a feature to `null` (`float(None)`); now a null or non-numeric feature
is an absent signal (0.0). Mock runs could not surface this.

### B6 — code-agent end-to-end recovery (DONE)

`scripts/run_e2e_code_agent.py` drove the code-agent target through the FULL
oracle ensemble in Docker, the catch-rate story the scored fraud target
structurally cannot show. Real run `704cdb13` (rounds=2, $5.77 on Max, 65 calls,
~13 min): the ensemble CAUGHT reward-hacks (black-box catch rate 0.50, white-box
1.00, so the informed attacker is caught more and the verifier does not rely on
surprise), 1 undetected reward-hack recorded; the blue round proposed a real
anti-reward-hack system prompt; before/after reward-hack pass-rate 0.50 to 0.50
(recovery 0.0 on the 2-payload sample, an honest small-sample result). Summary
in `artifacts/code_agent_e2e_summary.json`. Note the scaling limit: a 6-round
run made ~110 calls and ran past 2.5 hours, since the app shells out to the
`claude` CLI per call (~30 to 90s overhead each); keep code-agent runs small.
Docker must be running; uses the LOCAL Postgres, not prod.

## Remaining (1 item, needs a decision)

### D2 — weekly CI runs on cron (blocked on a merge)

`.github/workflows/ci-llm-weekly.yml` is shipped and correct (cron + dispatch,
both opt-in flags, fail-loud, log artifact). But a GitHub `schedule`/`dispatch`
workflow only runs from the **default branch `main`**, and `main` is 90 commits
behind under the do-not-merge constraint. D2 activates the moment the PR reaches
`main`; adding the file to `main` alone would only test stale code. Not touched.

## Operational runbook

- **Per-slice ritual:** `uv run ruff check . && uv run mypy . && uv run python
  scripts/check_module_imports.py && uv run pytest -q`, then a conventional
  commit with `--trailer "Assisted-by: Claude"`, `git push origin
  feat/crucible-build` (fans to GitHub + GitLab), then deploy.
- **Auto-deploy (D1):** a push to `feat/crucible-build` now triggers a Render
  deploy automatically via `.github/workflows/deploy.yml`, which calls the
  Render deploy API with the `RENDER_API_KEY` GitHub repo secret (set this
  session). No manual REST call needed. Manual fallback still works: see the
  curl in `REMAINING_WORK.md`.
- **Re-running the fraud e2e against prod:** it needs the external prod Postgres
  connection string in the gitignored `.env` as `CRUCIBLE_PROD_DATABASE_URL`
  (fetch via the Render API `connection-info` endpoint) AND your egress IP added
  to the `crucible-db` ipAllowList (I added then REMOVED `194.195.93.157/32`
  this session, so the allowlist is empty again). Run:
  `CRUCIBLE_RUN_LLM_TESTS=1 uv run python scripts/run_e2e_real_llms.py --real
  --target fraud --rounds 16 --budget 15 --db prod --api-base
  https://crucible-zaag.onrender.com`. The deployed read endpoints use the
  internal DB connection, so the empty allowlist does not affect the live site.
- **The prod is currently halted** (recall 0.0 from the real run), so `POST
  /runs` on the live service returns 409 by design. Lifting it requires recall
  back above 0.7, i.e. a hardened model behind the live target.

## Gotchas

- The `claude`-CLI-per-call overhead is the main scaling limit for any
  multi-call run (fraud ~64 calls is fine; the code-agent ensemble is not).
- An external sync process (the global graphify auto-update agent) has been
  renaming files (slice-04-honest-dashboard to slice-04-dashboard, with all
  references updated consistently), rewriting docs, and holding git
  `index.lock` mid-session. Stage only the specific files you own; clear a stale
  lock with `python3 -c "import os; os.remove('.git/index.lock')"` after
  confirming no git process is running.
- Stray files seen in the working tree from the code-agent run / sync process
  (`solution.py`, `frontend/live 2.js`) are untracked junk; do not commit them.
