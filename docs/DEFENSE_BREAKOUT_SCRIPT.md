# Crucible — 10-minute defense / breakout script

The as-built walk-through. It maps the demo arc in `acceptance-tests.md` section 4
onto the routes that actually ship. Two ways to run it:

- **Local, fully live** (the Claude Max CLI is authenticated): the red and blue
  loops call real models. Start Postgres and the app, then drive a run.
- **Deployed (Render), dashboard-live**: the deployed service runs `MOCK_LLM`
  (no Claude CLI on Render), so the dashboard, metrics, catalog, corpus, report,
  and halt routes serve real persisted data and SSE streams live; the live red
  attack is shown from the local run.

## 0. Bring it up (before the clock)

```bash
docker compose up -d --wait                 # Postgres
uv run alembic upgrade head                 # schema to head
uv run uvicorn orchestrator.api:app --port 8000
# open http://localhost:8000/app  (redirects to the Run Launcher, route "/")
```

The verbatim Claude Design bundle is served at `/app/*`; the live-data sidecar
swaps the stubbed numbers for the real backend and opens the SSE stream.

## 0 to 2 min — the problem

Two slides: silent wrongness in fraud detection, reward-hacking in code agents.
Manual review does not scale. Crucible certifies nothing; it reports a catch rate
against an adversary that already knows the verification scheme.

## 2 to 6 min — point the red agent at the fraud detector (live)

```bash
# create a run, then drive it (the loop runs the black-box then white-box pass)
RID=$(curl -s -XPOST localhost:8000/runs -H 'content-type: application/json' \
  -d '{"target_type":"fraud","artifact_ref":"fraud-v1","budget":{"max_attempts":4,"max_dollars":2.0},
       "spec":{"title":"evade the fraud detector",
               "obligations":[{"id":"o1","description":"the transaction is fraudulent but should score as legitimate"}]}}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["run_id"])')
curl -s -XPOST localhost:8000/runs/$RID/start
```

Open `/app/slice-04-dashboard.dc.html?run=$RID`: the ASR readout updates
live over SSE as attempts land. Click a verdict to open the per-oracle drill-down
(`/runs/$RID/verdicts/:vid`): four mechanical oracles plus the half-weight LLM
judge, US-4 evidence visible. The same red agent against the code-agent target is
where the oracle ensemble catches a reward hack.

## 6 to 9 min — trigger the blue loop

The proposed patch shows the adversarial training samples with provenance to the
catalog entries (`/blue/:patchId`). The held-out validation retrains and detection
recovers; `test_blue_fraud_recovery.py` proves it on real Kaggle data
(detection_before 0.0 → detection_after > 0 on held-out missed frauds). Replay the
same attack via `/app/slice-12-admin-debug.dc.html` and it is now blocked.

## 9 to 10 min — the numbers

- `/metrics` — black-box catch rate, white-box catch rate, and the gap side by
  side. The gap is the report card: a large gap means the verifier leaned on the
  attacker's ignorance.
- `/corpus.jsonl` — download the seeded-hack benchmark; row count equals the
  table count exactly.
- `/reports/$RID` — the SR 11-7 report; every number links to its Postgres row.
  `/reports/$RID.pdf` is the submittable PDF.
- Drop white-box recall below 0.70 and the red **Certification halted** banner
  appears on every route and `POST /runs` returns 409.

## Curl the deployed hash (Render)

```bash
curl -s https://<service>.onrender.com/health          # {"status":"ok",...}
curl -s https://<service>.onrender.com/metrics          # live catch rates
curl -s -o /dev/null -w '%{http_code}\n' \
  https://<service>.onrender.com/app/slice-04-dashboard.dc.html
```
