# Contributing

Read `constitution.md` first. This file translates the constitution's architecture and quality rules into the workflow rituals that keep them in force.

## 1. Branch naming

`<pillar>/slice-<N>-<short-title>`. Examples:

- `targets/slice-2-fraud-target`
- `red/slice-11-search-loop`
- `shared/types-add-confidence-field`
- `orchestrator/interfaces-add-replay-method`

The pillar prefix is one of `targets`, `oracles`, `red`, `blue`, `measure`, `shared`, `orchestrator`, `dashboard`. Anything else is rejected by the pre-merge check.

## 2. Squash-merge per slice (the revert-granularity contract)

Every slice lands on `main` as exactly one squash-merged commit. The commit message follows Conventional Commits:

```
feat(red): slice 11 — search loop with strategy catalog persistence

Closes US-6. Implements modules/red/search.py and modules/red/catalog.py
against orchestrator/interfaces/red.py.

Owner: <name>
Vouch report: tests/qa-reports/RUN_REPORT-slice-11.md (PASS)
Assisted-by: Claude
```

Why squash: reverting a slice is `git revert <one sha>`. Reverting a whole pillar is `git revert <list of that pillar's shas>`, scripted as `git log --oneline --grep "^feat(<pillar>):" | awk '{print $1}' | xargs git revert`.

## 3. Shared-folder changes ride their own branch (the discipline)

The rule: a pull request that touches `shared/types/` **must not** touch any `modules/<x>/` file. The pre-merge check `scripts/check_module_imports.py` rejects this combination.

The workflow:

1. The Red owner needs a new field `confidence: float` on `Attack`.
2. They branch `shared/types-add-attack-confidence` off `main`, edit only `shared/types/attack.py`, write the migration, run tests, open a pull request, merge.
3. They rebase their `red/slice-11-search-loop` on top of the new `main`, use the new field, open that pull request, merge.

If the shared change rides inside the Red slice's squash, reverting Red also reverts the type change, which silently breaks Oracles and Measure. The rule prevents that.

Exception: a slice that adds a brand-new shared type used only by that one slice (no other module has imported it yet) may ride together. The pre-merge check whitelists this case by detecting whether any other module already imports the changed shared file.

## 4. Interfaces in `orchestrator/interfaces/` are owned by the orchestrator

A pillar owner who needs an interface change opens a pull request against `orchestrator/interfaces/` only. The orchestrator owner reviews it against the integration tests. The pillar owner's slice rebases on top of the merged interface change.

A pillar owner who edits `orchestrator/interfaces/` inside their pillar slice is rejected by the pre-merge check.

The orchestrator's job is permanent, not one-shot. Interfaces evolve as pillar agents discover missing fields.

## 5. Module imports (the hexagonal rule, enforced)

A module may import only from:

- `shared/`
- `orchestrator/interfaces/`
- the Python standard library
- third-party packages declared in `pyproject.toml`

It may not import from any other module's package. `scripts/check_module_imports.py` walks the Abstract Syntax Tree (AST) of every file under `modules/<x>/` and rejects any `from modules.<y>` import where `y != x`.

## 6. Per-agent context scoping (for agent-team workflows)

Each pillar agent's working directory is the union of:

- `shared/`
- `orchestrator/interfaces/`
- `modules/<their-pillar>/`
- `tests/integration/test_<their-pillar>*.py`

No pillar agent reads code in another pillar's `modules/` directory. They read each other's interfaces; they never read each other's implementations.

The orchestrator agent's working directory is:

- `shared/`
- `orchestrator/`
- `tests/integration/` (the full directory)

## 7. Tests run on every commit

Local pre-commit hook (`prek` or `pre-commit`) runs:

```bash
ruff check . && mypy --strict . && pytest -x --no-header
```

Continuous Integration (CI) at `.github/workflows/ci.yml` runs the same plus coverage, the module-imports check, and the sandbox seal probe.

## 8. The submit-gate and `vouch` are mandatory

- Every code-touching response runs the submit-gate (`~/.claude/skills/submit-gate/SKILL.md`).
- Every slice that lands code runs `vouch` (`~/.claude/agents/vouch.md` plus this repo's `QA_ADVERSARY.md`) before the slice is reported done.

Reports live in `tests/qa-reports/` and are committed alongside the slice they grade.

## 9. AI-assistance trailer

Commits Claude wrote carry `Assisted-by: Claude` as a trailer. The trailer is added automatically by the agent loop checklist's commit step.

## 10. Pull request template

Every pull request body answers four questions:

1. **Which `spec.md` user story does this advance?** Cite the US-N identifier.
2. **Which `plan.md` component does this touch?** Cite the section.
3. **Which rubric pillar does this advance?** Cite the row of `spec.md` section 5.
4. **What did `vouch` say?** Link the `RUN_REPORT-<slice>.md` file. PASS or named blocking findings.

A pull request whose body does not answer all four is rejected by the bot, not the human reviewer.
