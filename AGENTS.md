# AGENTS — Crucible (quick card)

Automated AI red-team for AI agents the operator **owns**. Loop: **Profile → Attack → Gate → Fix → Re-eval → Report.**

**Read first:** `docs/PRD.md` (what/why), `docs/DESIGN.md` (how), `docs/PLAN.md` (beads `cr-*`). Full guide: `CLAUDE.md`.

**Five rules:** (1) operator-owned targets only; (2) fixes are diffs, never live; (3) never let the fix engine see the held-out set `H`; (4) reject fixes that cause over-refusal; (5) deterministic proof over LLM judgment.

**Tracking:** use `bd` (prefix `cr`), not markdown TODOs. `bd ready` → `bd update <id> --claim` → `bd close <id>`. Push before ending a session.
