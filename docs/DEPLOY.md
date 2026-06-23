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
- The LLM judge runs in **mock mode** (no `CRUCIBLE_REAL_JUDGE`), so the public
  endpoint makes **no LLM calls and incurs no cost**. The fraud loop is otherwise
  token-free. (Set `CRUCIBLE_REAL_JUDGE=1` + `OPENROUTER_API_KEY` to enable real Opus.)

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
