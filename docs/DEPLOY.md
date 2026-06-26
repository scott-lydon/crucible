# Deploy

The Integrity platform is deployed to the VPS via **systemd + Caddy** (deviation from
`plan.md §9`'s Render, tracked in bead `cr-dev`; matches the team's existing VPS
pattern). Live:

- **Dashboard:** <https://integrity-51-81-34-160.nip.io/app/>
- **API root:** <https://integrity-51-81-34-160.nip.io> (`/` → `/app/`)

## Topology

```
Caddy (:443, auto-TLS)  →  uvicorn orchestrator.api:app (127.0.0.1:8110)
                               ├─ StaticFiles  → frontend/ (dashboard)
                               └─ Postgres 16  → docker crucible-pg (127.0.0.1:55432)
```

The FastAPI app serves both the JSON API and the static dashboard (same origin, so the
front end's `live.js` calls the API with no CORS).

## Service

`/etc/systemd/system/crucible-integrity.service` (a copy lives at
`deploy/crucible-integrity.service`):

- `WorkingDirectory=/home/ubuntu/crucible-rebuild`, runs the venv uvicorn on `:8110`.
- `DATABASE_URL` → the dockerized Postgres on `:55432`.
- `CRUCIBLE_HALT_RECALL=0.0` on the public instance so the halt gate never blocks demo
  re-runs (the halt rule is fully exercised in tests at the default 0.7). Raise it to
  demonstrate halt-certification.
- **Real Claude is ON (cr-f5).** The unit sets `CRUCIBLE_REAL_RED/JUDGE/BLUE/AGENT/
  HELDOUT/DIFFERENTIAL/SPEC=1`, so the live loop runs the real AI attacker (Sonnet), the
  real agent under test (Sonnet), the real defender (Sonnet), and the Opus judge / held-out
  / differential. The OpenRouter key is read from `~/.config/crucible/openrouter.key` by
  `shared/config.py` — **no key is stored in the unit**.
- **Budget cap (cr-f4) makes this safe:** `CRUCIBLE_GLOBAL_BUDGET=15.0` is a hard ceiling
  on total real-LLM spend across all runs. Once reached, `POST /runs` returns 402 and any
  in-flight run halts; each run is additionally bounded by its own `budget_dollars`. Check
  the meter at `GET /budget`. To make the public endpoint free again, drop the
  `CRUCIBLE_REAL_*` env lines and restart. The fraud demo is token-free regardless.

## Caddyfile block

```
integrity-51-81-34-160.nip.io {
	reverse_proxy 127.0.0.1:8110
}
```

## Operations

```bash
# logs / status
sudo journalctl -u crucible-integrity -f
sudo systemctl status crucible-integrity

# redeploy after pulling code
cd /home/ubuntu/crucible-rebuild && git pull
.venv/bin/alembic upgrade head            # apply any new migrations
sudo systemctl restart crucible-integrity # ~3s boot (rebuilds the wired container)

# (re)train models if artifacts/ is empty
.venv/bin/python -m modules.targets.fraud.train
.venv/bin/python -c "from modules.oracles.differential.model import ensure_isoforest; ensure_isoforest(1)"
```

The Postgres data and the trained `artifacts/` (gitignored) persist on the host across
restarts; only code + migrations change on redeploy.
