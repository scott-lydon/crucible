# Contributing to Crucible

Thanks for your interest in Crucible. This guide covers setup, tests, and the
pull-request flow.

## Development setup

Crucible runs on Python 3.12+ with Postgres via Docker.

1. Install dependencies with uv: `uv sync`
2. Start Postgres: `docker compose up -d`
3. Apply migrations: `uv run alembic upgrade head`
4. Run the API: `uv run uvicorn orchestrator.api:app --reload`

## Running the tests with no API key

Crucible is mock-first. The full suite runs offline against a deterministic
scripted model, so you do not need an Anthropic or OpenRouter key to contribute:

    uv run pytest

To exercise the real models, put the relevant keys in a local `.env` (see
`.env.example`) and set the `CRUCIBLE_REAL_RED` and `CRUCIBLE_REAL_HELDOUT` flags.

## Code style

- Python 3.12+, full type hints, checked with `mypy --strict`.
- No mock, stub, or placeholder data in production code paths. Tests use the
  scripted model; production paths use real data.
- Errors fail loud with typed, specific exceptions. Do not catch and swallow.
- Conventional Commits for messages: `type(scope): subject`.

## Pull requests

1. Branch from `main`.
2. Keep each pull request to one logical change.
3. Make sure `uv run pytest` passes.
4. Open the pull request against `main` with a clear description of what and why.

## Reporting security issues

Please do not open public issues for vulnerabilities. See SECURITY.md.
