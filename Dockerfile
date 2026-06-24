# Crucible deploy image (Render web service, US-1/US-2 dashboard + API).
#
# Native Python on the host has no libgomp, which LightGBM needs at import, so we
# control the system libs here. The committed fraud model artifact ships in the
# image; the Claude CLI is not present on Render, so the deploy runs MOCK_LLM
# (the run header marks any mock run, US-15) and the dashboard, metrics, catalog,
# corpus, report, and halt routes all serve real persisted data.
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

ENV MOCK_LLM=true PYTHONUNBUFFERED=1

# Run migrations to head, then serve. $PORT is provided by Render.
CMD ["sh", "-c", "alembic upgrade head && uvicorn orchestrator.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
