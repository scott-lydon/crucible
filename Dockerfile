# Crucible deploy image (Render web service, US-1/US-2 dashboard + API).
#
# Native Python on the host has no libgomp, which LightGBM needs at import, so we
# control the system libs here. The committed fraud model artifact ships in the
# image. The Claude CLI is not present on Render, so live runs fall back to the
# Anthropic Messages API using a key supplied through the admin panel (the
# project ANTHROPIC_API_KEY after admin login, or a visitor's own key); MOCK_LLM
# is therefore off by default here and set per-service by Render. On boot, when
# CRUCIBLE_SEED_DEMO=true, scripts/seed_demo.py loads a captured real-LLM
# snapshot so the dashboard, metrics, catalog, corpus, report, and halt routes
# serve real persisted data.
FROM python:3.12-slim

# libgomp1 is LightGBM's OpenMP runtime; without it `import lightgbm` fails.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Core plus the ml group (LightGBM, scikit-learn, scipy, numpy, pandas), which
# the fraud target, the hybrid red fallback, and the blue retrainer import.
RUN pip install --no-cache-dir ".[ml]"

ENV PYTHONUNBUFFERED=1

# Migrate to head, seed the demo snapshot (idempotent + gated by
# CRUCIBLE_SEED_DEMO; no-op otherwise), then serve. $PORT is provided by Render.
CMD ["sh", "-c", "alembic upgrade head && python scripts/seed_demo.py && uvicorn orchestrator.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
