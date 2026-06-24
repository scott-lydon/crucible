# QA Adversary playbook for Crucible

How the `vouch` sub-agent attacks this repository. This file is the
authoritative override on the generic playbook; if it is still a template,
the sub-agent has no project anchor and silently runs the generic checks.

## Test commands

```bash
# Full suite (needs Postgres up: `docker compose up -d`).
uv run pytest -q

# Static gates.
uv run ruff check .
uv run mypy .
uv run python scripts/check_module_imports.py

# Slice 0 done-criterion in isolation.
uv run pytest tests/integration/test_smoke.py::test_post_runs_returns_run_id -q
```

## Base branch for diff

`origin/main`. The integration branch is `feat/crucible-build`. Diff a slice
with `git diff origin/main...HEAD` (or `HEAD~1...HEAD` for the latest slice).

## Named bug categories to hunt

1. **Fake or reused data.** Any oracle verdict, metric tile, catalog entry,
   corpus row, or SR 11-7 figure that is not computed from a real run. A "0.0"
   default where "Not yet measured" is required (US-10). The fraud target
   trained on anything other than the real Kaggle credit-card dataset.
2. **Swallowed exceptions.** A `try/except` in business logic that logs and
   continues instead of letting the error ride to the loop. Catch sites are
   allowed only at the FastAPI boundary and the sandbox-job entry
   (coding-practices.md section 6).
3. **Cross-module imports.** `from modules.<x>` inside `modules/<y>/`. The
   guard is `scripts/check_module_imports.py`; confirm it actually fails on a
   planted violation.
4. **Silenced types.** Any `# type: ignore` without a ticket reference, any
   `cast(...)` used to dodge a real type mismatch, any new mypy baseline entry.
5. **Non-deterministic replay.** A verdict, attack, or oracle vote whose
   Replay (US-5) diverges from the original. Every persisted row must capture
   its seed.
6. **Oracle collusion / shared blind spots.** Two oracles that fail the same
   way on the same input. The white-box self-test (US-14) is rewarded for
   finding a shared gap; confirm it actually runs every pass.
7. **Sandbox seal leak.** The producer container resolving Postgres, the Modal
   control plane, or the verification bucket. `tests/integration/test_sandbox_seal.py`
   must prove all three time out (slice 4).
8. **Stale-frontend wiring.** A dashboard route that reads from the loop
   instead of from Postgres via the SSE backend, or a built bundle that does
   not reflect the source change (DEPLOY-VERIFY).

## Hot files (recent churn)

`shared/types/*`, `shared/persistence/models.py`, `orchestrator/api.py`,
`orchestrator/interfaces/*`. Refresh with
`git diff --name-only HEAD~15..HEAD` before each pass.

## Conventions

- Failing tests go under `tests/` mirroring the module path; integration tests
  that need the loop go under `tests/integration/`.
- The QA agent has Read/Grep/Glob/Bash only. A bug surfaces as a failing test
  or a written report, never a silent patch.

## Ignored paths

`_design_bundle/`, `frontend/`, `website/`, `docs/design-screenshots/`,
`design/`. These are the Claude Design export and the static architecture
site, not backend code paths.

## End-to-end pipeline command

```bash
docker compose up -d
uv run alembic upgrade head
uv run pytest -q
```

## Where to write reports

`docs/qa/RUN_REPORT.md` (create the directory if missing). One report per
pass, dated, with the diff range it covered at the top.
