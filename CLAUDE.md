# Project Instructions for AI Agents — Crucible

Crucible is an automated AI red-team: it attacks an AI agent the operator **owns** (prompt injection, jailbreaks, secret exfiltration, tool abuse), proves each break, proposes/applies fixes as reviewable diffs, and re-evaluates on held-out attacks to prove the fix generalized.

> The Gas Town beads-integration block is injected by `gt rig add`. Use `bd prime` for the issue-tracker workflow. Bead prefix: **`cr`**.

## Golden rules (do not violate)

1. **Operator-owned targets only.** This is a *defensive* tool. Never add functionality whose headline use is attacking systems the user does not own. Default config refuses arbitrary public targets.
2. **Fixes are diffs, never live.** The fix engine emits patches / opens a branch. It never mutates a running target.
3. **The held-out firewall is sacred.** The fix engine must never see the held-out attack set (`H`). They live in separate components; sharing them makes the eval circular and worthless.
4. **No over-refusal.** A fix is accepted only if it stops the attack **and** preserves benign behavior (utility regression check). Security that breaks the product is a failed fix.
5. **Proof over opinion.** Prefer deterministic oracles (canaries, tool-call interception, guardrail-fired signals) over an LLM judge. The judge is one measured signal, never the sole authority.

## Where things live

- Requirements: `docs/PRD.md` · Design: `docs/DESIGN.md` · Plan & beads: `docs/PLAN.md` · Corpus sourcing: `docs/SOURCES.md`
- The canonical deep design (pre-rig) is also mirrored at `~/crucible_design.md`.

## Build & test

_Stack: Python (see `docs/DESIGN.md`). Commands below are the intended convention; scaffold bead `cr-1` establishes them._

```bash
# uv venv && uv pip install -e ".[dev]"
# pytest                 # unit + integration
# ruff check . && ruff format --check .
# mypy src/
```

## Definition of done (per bead)

- Tests pass; lint + types clean.
- For attack/oracle/fix beads: a deterministic test proving the behavior (e.g. canary leak detected, fix raises held-out catch rate).
- No secrets committed; vendored attack corpora carry a recorded license (see `docs/SOURCES.md`).
- Issue closed in `bd`, work pushed.

## Conventions

- Python 3.12+, type hints everywhere, structured (typed) findings — no free-text-only results.
- LLM provider pluggable; default Claude, BYO API key; never hard-code keys.
- Every attack carries its oracle and its proof in the result object.
