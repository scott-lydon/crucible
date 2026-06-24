# Crucible — handoff

Branch `feat/crucible-build`, HEAD **`8391dd3`** (local == GitHub == GitLab, verified
via `git ls-remote`). Slices 0 through 19 are built; the only open item is the
live Render instance, which is blocked on Render credentials (none exist on this
machine). Everything else is done, gated, committed, and dual-pushed.

## State of the gates (all green at 8391dd3)

```
uv run ruff check .                       # clean
uv run mypy .                             # clean (141 source files)
uv run python scripts/check_module_imports.py   # clean (no cross-module / no shared/types co-edit)
uv run pytest -q                          # 134 passed, 7 skipped (opt-in live/slow)
```

Opt-in proofs that have passed live (set the env var to re-run):
- `CRUCIBLE_RUN_LLM_TESTS=1` — `test_white_box_live.py` (real Opus white-box red,
  oracle scheme injected, no refusal), `test_hybrid_live.py` (real Sonnet sweep +
  scipy against the committed fraud model).
- `CRUCIBLE_RUN_SLOW_TESTS=1` — `test_blue_fraud_recovery.py` (real Kaggle retrain;
  detection on held-out missed frauds recovers from 0.0).

## What each slice delivered

- **12 white-box red:** `modules/red/white_box.py` builds the disclosed oracle
  scheme from each oracle's `protocol_description`; `RedSearchAgent` injects it and
  runs the informed pass on Opus. Red is wired into `orchestrator/loop.py` (black-box
  then white-box pass). `/metrics` reports black-box vs white-box catch rate + gap
  (`modules/measure/metrics.py`).
- **13 hybrid fallback:** `modules/red/hybrid.py` — after 3 caught rounds, an LLM
  picks a sensitivity-analysis sweep and `scipy.optimize.differential_evolution`
  runs it (async target scored from a worker thread via `run_coroutine_threadsafe`).
  Reframed to benign sweep language because the model refuses an "evasion-region"
  ask (see `crucible-adversarial-llm-refusal` memory).
- **14 blue loop:** `modules/blue/` proposer + retrainer (`fraud-vN.lgb` / versioned
  `agent_configs`) + held-out validator (`HoldoutContamination` guard). Tables
  `blue_patches`, `model_versions`, `holdout_runs`, `agent_configs`.
- **15 dashboard wiring:** the verbatim Claude Design bundle in `frontend/` is served
  at `/app/*` with a `live.js` sidecar injected at serve time (UI byte-identical,
  only stubbed DATA swapped via `data-live` hooks + SSE). Real routes: `POST
  /runs/:id/start`, `GET /runs`, `GET /runs/:id`, `GET /runs/:id/verdicts/:vid`,
  `GET /blue/:patchId`, real SSE `GET /runs/:id/stream`. Per-oracle tables
  `judge_votes`, `fuzz_findings`, `differential_runs` populated by the loop.
- **16 corpus export:** `GET /corpus` + `GET /corpus.jsonl` (line count == table count).
- **17 SR 11-7 report:** `GET /reports/:runId` (Markdown, numbers link to row routes)
  + `GET /reports/:runId.pdf` (dependency-free `modules/measure/pdf.py`).
- **18 halt-cert:** `modules/measure/halt_rule.py` sets the `halt_state` flag when
  white-box recall < 0.7; `POST /runs` returns 409; `GET /halt` + the `live.js`
  banner on every route.
- **19 demo polish:** `docs/DEFENSE_BREAKOUT_SCRIPT.md`, `AI_INTERVIEW_PREP.md`,
  `website/index.html` as-built; `Dockerfile` + `render.yaml` + `.dockerignore`.

## The one open item: a live Render instance

Verified blocker: `render whoami` says "run `render login`"; no `~/.render`,
`~/Library/Application Support/render`, or `~/.config/render`; no `RENDER_API_KEY`
in the environment. The CLI cannot reach a Render account, so no deploy is possible
from here, and a fabricated URL is not acceptable.

The deploy artifact is proven locally end to end: the 859MB `crucible:deploy` image
was built, run against a fresh Postgres, applied all nine migrations from scratch,
booted, served `/health` `/metrics` `/halt` and the verbatim `/app` pages, and drove
a full run to `complete` under `MOCK_LLM`.

### To go live (pick one)

1. **Render Dashboard Blueprint (browser):** `dashboard.render.com` -> New ->
   Blueprint -> connect `github.com/scott-lydon/crucible`, branch
   `feat/crucible-build`. It reads the committed `render.yaml` (Docker web service +
   free Postgres; migrations run on container start). Then `curl <url>/health`.
2. **Render API key (fully scriptable):** create a key at
   `dashboard.render.com/u/settings#api-keys`, then drive the Render REST API to
   create the Postgres + web service from `render.yaml`'s spec and poll the deploy.
3. **CLI login (interactive):** `render login`, set a workspace, then create the
   service (`render services create`) and a managed Postgres; wire `DATABASE_URL`.
   Note: the v2 CLI has no one-shot `blueprint launch`, so paths 1 or 2 are simpler.

### Verify once live

```bash
curl -s https://<service>.onrender.com/health     # {"status":"ok","database":"connected"}
curl -s https://<service>.onrender.com/metrics
curl -s -o /dev/null -w '%{http_code}\n' https://<service>.onrender.com/app/slice-04-honest-dashboard.dc.html
# confirm the deployed commit matches 8391dd3 (Render dashboard "Deploys" tab)
```

### Render caveats to watch

- The Claude CLI is not on Render, so the service runs `MOCK_LLM=true`; the dashboard
  and every read route serve real persisted data and SSE, but a live red/blue
  walk-through is a local-only demo (the local `claude` CLI is authenticated).
- The 144MB `data/creditcard.csv` is gitignored and absent on Render, so blue
  **retrain** is local-only; the committed `artifacts/fraud-v1.lgb` ships in the image.
- `render.yaml` wires `DATABASE_URL` from the managed Postgres `connectionString`
  (internal, no SSL param needed for asyncpg); `Dockerfile` installs `libgomp1` for
  LightGBM.

## Run locally

```bash
docker compose up -d --wait
uv run alembic upgrade head
uv run uvicorn orchestrator.api:app --port 8000
# http://localhost:8000/app  (redirects to the Run Launcher)
```

Full demo walk-through: `docs/DEFENSE_BREAKOUT_SCRIPT.md`.

## Submit-gate status

NOT READY on exactly one criterion: "dashboard walks the demo on a live Render
instance (curl the deployed hash)." Every other check passes (gates green, HEADs
matched at `8391dd3`, no stubs on user paths, no catch-log-continue, deploy image
verified locally). It flips to READY the moment the hosted instance answers on
`8391dd3`.
