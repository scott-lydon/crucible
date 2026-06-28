# Crucible — RESUME PROMPT (read this first)

You are Claude Code (Opus 4.8, 1M ctx) resuming an autonomous build on this VPS for **Julian**
(julianstancioff@gmail.com). Your memory was wiped; **this file + the repo are your source of
truth.** Do NOT restart, re-plan, or rebuild — everything below already exists and is LIVE.

## What Crucible is
A self-serve tool to stress-test ANY AI agent: a real AI **attacker** (Claude) red-teams it, an
independent **5-oracle checker panel** grades every output for silent failure, and a real AI
**defender** (Claude) hardens it, co-evolving over rounds → a **trust score + risk report (PDF) +
weakness catalog**. Point it at a demo agent, a BYO model+prompt, a deployed HTTP endpoint, or a
**sandboxed code-agent that writes AND runs Python**.

## STATUS (2026-06-27): BUILT, TESTED, LIVE, PUSHED
- All milestones A–F done + launcher completion (code-agent, BYO HTTP, YAML, hidden tests).
- **170 tests green**; ruff + mypy --strict + arch-check clean.
- **Live:** https://integrity-51-81-34-160.nip.io/ (SPA dashboard at `/app/`), real Claude on,
  ~$2.6 of the $15 cap spent.
- **Pushed:** branch `julian/integrity-rebuild` on `scott-lydon/crucible` — 0 unpushed.

## ENVIRONMENT
- Repo `/home/ubuntu/crucible-rebuild`, branch `julian/integrity-rebuild`, venv `.venv`.
  Start every bash block: `cd /home/ubuntu/crucible-rebuild && source .venv/bin/activate` (cwd/env
  do NOT persist between calls).
- **DB:** docker `crucible-pg` at `127.0.0.1:55432` (user/pw/db = `crucible`; tests use
  `crucible_test`, made by conftest). **9 tables** (runs, specs, attacks, verdicts, llm_calls,
  sandbox_jobs, health_probes, agent_configs, coevolution_rounds). Alembic head includes
  `runs.agent_config_id` + `runs.target_http`.
- **Live service:** systemd `crucible-integrity` (:8110) + Caddy → the URL above. Runs FROM the
  working dir, so deploying = `sudo systemctl restart crucible-integrity`. Frontend is static
  (served fresh, `Cache-Control: no-store`) — no restart needed for `frontend/` edits.
  Logs: `sudo journalctl -u crucible-integrity -f`.
- **LLM:** OpenRouter key at `~/.config/crucible/openrouter.key` (auto-read by `shared/config.py`).
  Models: `anthropic/claude-sonnet-4.6` (red/blue/agent), `anthropic/claude-opus-4.8` (judge/
  held-out/differential). Live service has ALL real flags set: `CRUCIBLE_REAL_RED/JUDGE/BLUE/AGENT/
  HELDOUT/DIFFERENTIAL/SPEC=1` + `CRUCIBLE_GLOBAL_BUDGET=15.0` + `CRUCIBLE_HALT_RECALL=0.0`.
  NOTE: `AnthropicClient` is only a docstring, NOT implemented — `make_llm` is OpenRouter-only
  (and OpenRouter works, so Anthropic isn't needed).
- **Browser verify** (the MCP browser is usually locked by other sessions): `pip install playwright`
  is already done; drive the cached chromium directly —
  `/home/ubuntu/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome` with `args=["--no-sandbox"]`,
  hash routes like `…/app/#/dashboard/<runId>`.
- **Beads (Gas Town):** `cd /home/ubuntu/gt/crucible && export PATH=$PATH:/home/ubuntu/go/bin &&
  export BEADS_ACTOR=claude && bd ready`. Epics `cr-agent` + `cr-ui` CLOSED; only `cr-dev` open.

## HOW TO OPERATE
- **Gate before EVERY commit (all green):** `ruff check . ; mypy shared orchestrator modules scripts ;
  python scripts/check_module_imports.py ; pytest tests/ -q`.
- **Commits:** Conventional + trailers `Assisted-by: Claude` and
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. NEVER commit to `main`.
- **Push:** works with the current `repo` scope for normal changes. Anything touching
  `.github/workflows/` is REJECTED (token lacks `workflow` scope). The CI config is parked at
  `docs/ci-workflow.yml.txt`; restore it after `gh auth refresh -h github.com -s workflow` via
  `git mv docs/ci-workflow.yml.txt .github/workflows/ci.yml`.
- **Honesty rule:** never fake metrics/data; report residuals plainly. Manual live testing keeps
  finding real bugs — keep doing it, and verify before claiming "done".

## ARCHITECTURE (one loop, 5 pluggable pillars behind `orchestrator/interfaces/`)
`RED (attacker) → TARGET (the agent) → PANEL (5 oracles) → verdict`, and in co-evolution mode
`→ BLUE (defender rewrites the system prompt) → repeat`. Target kinds: `agent` (support-bot/coder
demos + BYO model+prompt + BYO HTTP endpoint via `runs.target_http`), `code_agent` (writes Python,
runs it in `LocalDockerSandbox --network none`), `fraud`, `dummy`. Oracles: held_out (hidden checks
= ground truth), differential, metamorphic (re-queries the run's target — `Retargetable`), property_
fuzz/consistency, llm_judge. `POST /runs` modes: `redteam` | `coevolution`. **Trust score** =
`1 - failures/attacks`, where a failure = caught OR held-out-fired; silent failures (held-out fired
& not caught) are surfaced separately. Deeper detail: `docs/PLAN_AI_AGENT_TESTING.md`,
`docs/DEPLOY.md`, `docs/DEMO.md`.

## TEAM / DEMO CONTEXT (a team project with a Sun-noon freeze)
- Repo `scott-lydon/crucible`. Team: **Scott Lydon** (lead), **Gustavo Hornedo**, **Julian** (you
  report to Julian). Timeline: **Sat** integrate + rehearsal, **Sun** 10-min timed rehearsal,
  **freeze by noon**.
- **Canonical branch = `julian/integrity-rebuild`** (9 tables). PR #3 is a DIFFERENT 20-table
  schema — NOT canonical; its `render.yaml` / `CRUCIBLE_SEED_DEMO` seed-from-JSON mechanism is NOT
  on our branch.
- **Deploy-target risk:** Scott plans to deploy to **Render** with a seed JSON; we're already live
  + validated on the **VPS**. Recommend demoing from the VPS (already populated with real data) OR
  porting Render NOW with time to test + seed via `pg_dump` (matches the 9-table schema), not Sat
  night.
- Gustavo's QA will find: 170 integration tests pass on real Postgres; the 5 oracles DO catch bad
  outputs (proven live — a leaky agent was caught by 4/5); trust gives real A–F; halt-cert only
  triggers if `CRUCIBLE_HALT_RECALL` is raised >0.7 (live runs at 0.0).

## WHERE I AM RIGHT NOW (pick up here)
- Demo-seed task RESOLVED (2026-06-27). Ran two NEW co-evolution runs vs a deliberately weak
  Claude-sonnet-4.6 support-bot (BYO model+prompt; payload at `data/demo_seed_run.json`):
  - `run_a5b4f61d3558` (4 attacks/round): ASR **1.00→0.75→0.25→0.75** — best honest seed; net 4×
    drop with a real attacker-recovery bounce. trust 25/F, 9 silent failures. **USE THIS for the
    co-evolution beat.**
  - `run_4f8427530235` (8 attacks/round, refined): ASR **flat 0.125** all 4 rounds. CONCLUSION: a
    real safety-trained model's round-0 leak rate is ~12% and noisy — a clean monotonic "100→0"
    curve would be small-sample cherry-picking. DO NOT chase a prettier curve; the noise is inherent.
- Demo strategy decided + written: **`docs/DEMO_RUNSHEET.md`** (timed 10-min script, all real IDs).
  Lead with the reliable wow, not the curve: verdict `vdt_c849693cac6f` (run `run_998e38597826`) —
  a jailbroken support-bot leaks another customer's PII + a $4000 refund, **panel catches it 4/5**.
  SR 11-7 PDF verified generating. Demo from the VPS, not a fresh Render deploy.
- Budget after these runs: ~$5.5 of $15 spent (~$9.5 left). All DB writes are real, no fakes.
- Open (Julian's call): (a) commit/push `docs/DEMO_RUNSHEET.md` + RESUME edits (not done — push needs
  his ok); (b) prep `pg_dump` so Render is a real fallback to the VPS.

## HONEST RESIDUALS / what's left
1. A full **manual QA pass** (it's the only thing finding real bugs — most recently the trust score
   wrongly showing 100/A for a caught-but-always-failing agent; fixed so it now reads 0/F).
2. **Code-agent co-evolution** (AI defender for code agents) — deferred; needs per-kind target
   factories (`container.target_factory_for(kind)`). Red-team for code agents works fully.
3. **Re-activate GitHub Actions CI** on the branch (config parked; needs `workflow` scope).
4. **Production hardening** if multi-user: concurrent runs share oracle/red/blue instances
   (per-run priming/retargeting is racy); no auth on the public URL (only the budget cap protects it).
