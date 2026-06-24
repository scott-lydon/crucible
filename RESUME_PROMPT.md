You are Claude Code resuming a long, autonomous build on this VPS. Pick up exactly where the last context left off — do NOT restart, re-plan, or rebuild what exists.

MISSION: Finish building **Crucible** — a self-serve tool to stress-test ANY AI agent: a real AI **attacker** red-teams the agent, an independent **checker panel** grades every output for silent failure, and a real AI **defender** hardens it, co-evolving over rounds → a trust score + risk report + weakness catalog. The plan is written and approved; the engine is already built and deployed live. Execute the remaining milestones, reusing the engine.

DO THIS FIRST, IN ORDER:
1. Read `/home/ubuntu/crucible-rebuild/docs/PLAN_AI_AGENT_TESTING.md` — the canonical plan (problem statement, reuse map, milestones A–F, tasks, resume steps). Source of truth.
2. Read your project memory note `crucible-redteam.md` (auto-loaded; else `/home/ubuntu/.claude/projects/-home-ubuntu/memory/`).
3. Start every bash block with: `cd /home/ubuntu/crucible-rebuild && source /home/ubuntu/crucible-rebuild/.venv/bin/activate` (cwd/env do NOT persist between calls).
4. `cd /home/ubuntu/gt/crucible && export PATH=$PATH:/home/ubuntu/go/bin && export BEADS_ACTOR=claude && bd ready` → claim the next task with `bd update <id> --claim`. It starts at **cr-a1** (the generic AgentTarget adapter).
5. Then BUILD autonomously, milestone by milestone (A→F). Do not stop for approval — the plan is approved. Keep going across the whole plan.

ENVIRONMENT:
- Repo `/home/ubuntu/crucible-rebuild`, branch `julian/integrity-rebuild`, venv `.venv`. For LLM calls: `export OPENROUTER_API_KEY=$(cat ~/.config/crucible/openrouter.key | tr -d '[:space:]')`.
- Postgres: docker `crucible-pg` at `127.0.0.1:55432` (user/pw/db = crucible); tests use DB `crucible_test` (conftest creates it).
- Live: systemd `crucible-integrity` (:8110) + Caddy → https://integrity-51-81-34-160.nip.io (dashboard /app/). `sudo systemctl restart crucible-integrity`; `sudo journalctl -u crucible-integrity`.
- LLM via OpenRouter: `anthropic/claude-sonnet-4.6` (red/blue inner loops), `anthropic/claude-opus-4.8` (judge, white-box, held-out generation). Flags `CRUCIBLE_REAL_RED=1` / `CRUCIBLE_REAL_JUDGE=1` switch free mock → real Claude. Cost is no object — BUT build the budget cap (cr-f4) BEFORE enabling real Claude on the PUBLIC site (cr-f5).
- Team's design export to integrate in Milestone E: `/home/ubuntu/GitHub Crucible Repository-2` (Graphite Meridian).
- Push blocked: gh token lacks `workflow` scope. Commit locally; don't block on push. Ask Julian once to run `gh auth refresh -h github.com -s workflow` (then push the ~18 commits).

STANDING RULES:
- Gas Town **beads** for ALL tracking (`bd`, never TodoWrite/TaskCreate): `bd ready` → `bd update --claim` → build → gate → `bd close <id>`. Run `bd` from `/home/ubuntu/gt/crucible`.
- Quality gate before EVERY commit, all green: `ruff check .`; `mypy shared orchestrator modules scripts`; `python scripts/check_module_imports.py`; `pytest tests/ -q`. Commit only once a task is PROVEN (run it, observe it).
- Conventional Commits + trailers `Assisted-by: Claude` and `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. One task ≈ one commit. NEVER commit to `main`.
- NEVER fake metrics or mock data in integration tests (real Postgres only). Be honest about residuals — Julian values honesty over a flashy number.
- REUSE the built engine (loop, 5 oracles, aggregator, sandbox, measure API, LLM client, deploy, fraud demo). The 5 pillars are interfaces (`orchestrator/interfaces/`) — new pieces plug into the same ports via `wiring.py`. Do not rebuild.
- Keep memory + the plan doc current as milestones land. Update Julian at milestone checkpoints; otherwise keep building.

NORTH STAR: "anyone points it at their AI agent and watches two of our AI agents red-team it, ending in a trust score they can stand behind." Fraud is now just a built-in demo; the agent target is the product. Build that.
