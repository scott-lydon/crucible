# Crucible — Active Build Plan: "Stress-test ANY AI agent" (AI-vs-AI re-center)

> This is the **canonical execution plan** as of 2026-06-24. It supersedes the earlier
> fraud-first slice order and the `cr-v2`/`cr-m1..m5`/`cr-t01..t20` beads (deleted). It is
> faithful to the team's `spec.md` (which always called for a target-agnostic platform and
> a code-agent target) — it only **re-prioritizes execution** around the real product.
> A fresh context should read THIS file + run `bd ready`, then build.

---

## 1. Problem statement (read this first)

AI systems fail **silently**: they return a confident answer that is simply wrong — no
error, no flag — and nobody notices. Anyone betting money, safety, or reputation on an AI
(a bank's fraud model, a company's customer-service bot, a team's coding assistant) has no
trustworthy way to answer the one question that matters: **"How often does this AI fail in
a way that slips past every check we have — and can you prove it?"** "It passed our tests"
proves little, because the tests often share the AI's blind spots.

**Crucible is a crash-test lab for AI.** A user brings their AI agent and a few plain-English
lines describing its job. Then:

1. A real **AI attacker** (Claude) red-teams it — reasons about how to make it fail, crafts
   adversarial inputs, adapts when caught, and names the tactics it discovers.
2. A panel of **independent checkers** (the oracle ensemble) grades every output for silent
   failure — and crucially is *not allowed* to share the attacker's blind spots.
3. A real **AI defender** (Claude) reads the weaknesses and **hardens** the agent (rewrites
   its instructions/guardrails — you can't retrain a rented model), then re-validates on
   attacks it never saw.
4. The loop **co-evolves** over rounds; you watch two AIs duel under a referee.
5. Output: a **trust score** (how leaky it is even against an attacker who knows the
   checkers' playbook), a **risk report**, and a **catalog of every weakness found**.

**The re-centering requirement (the thing that was missing):** the red and blue must be
**real, reasoning AI agents**, and the target must be **ANY user-supplied AI agent**, not
just the built-in fraud model. "Anyone can point it at their AI and watch two of our AI
agents red-team it."

## 2. End state — what "done" looks like

A self-serve Graphite-Meridian dashboard (the team's design export at
`~/GitHub Crucible Repository-2`). A user: (a) picks a model or brings their own agent +
system prompt, (b) writes a short spec of the job + what counts as failure, (c) hits Start,
(d) watches the AI attacker's reasoning stream, attacks get judged, the AI defender patch,
and the co-evolution curves move, (e) ends on a trust score + downloadable report +
weakness benchmark. Real Claude drives red, blue, judge (behind a budget cap). The fraud
model remains a one-click built-in demo.

## 3. The honest design insight (why this is also the RIGHT engineering call)

Agents are **natural language**, so the LLM attacker/defender operate **directly** — clean,
dramatic AI-vs-AI. The fraud model was the **bounded** case (anonymized PCA features force a
hybrid LLM+`scipy` attacker whose evasions are capped and whose retrain doesn't generalize —
an honest residual we proved). So re-centering on "any agent" is exactly where the AI
actually shines. Fraud stays as a built-in demo; the agent target is the product.

## 4. What is ALREADY BUILT (reuse — do NOT rebuild)

17 slices, deployed live at https://integrity-51-81-34-160.nip.io, 35 tests green:
- **Engine:** `orchestrator/loop.py` (red→verify→harden→measure + black-box & white-box
  passes, co-evolution-ready), the 5 interface ports (`orchestrator/interfaces/`), DI
  `wiring.py`, FastAPI `api.py` (+ SSE), `shared/persistence` (async Postgres + Alembic).
- **Verification ensemble:** `modules/oracles/{held_out,differential,metamorphic,property_fuzz,
  llm_judge}` + `aggregator.py` (vote-weighted, threshold 2.0).
- **Sandbox:** `shared/sandbox/` (Docker `--network none` seal + probe) — for code execution.
- **LLM client:** `shared/llm/` (OpenRouter Sonnet 4.6 / Opus 4.8, ScriptedLLM mock, cost).
- **Measure API:** `/metrics /verdicts/:id /corpus /catalog /reports/:id /halt`.
- **AI red (fraud):** `modules/red/llm_hybrid.py` (LLM strategy + `scipy` perturbation) — DONE.
- **Blue (fraud retrain):** `modules/blue/agent.py` — DONE (honest: doesn't generalize).
- **Deploy:** systemd `crucible-integrity` + Caddy; `docs/DEPLOY.md`.
- **Fraud + dummy targets:** `modules/targets/{fraud,dummy}`.

Flags: `CRUCIBLE_REAL_RED=1` (Sonnet attacker), `CRUCIBLE_REAL_JUDGE=1` (Opus judge),
`CRUCIBLE_HALT_RECALL` (red line). All mock on the live service today (free).

## 5. Architecture decisions for the agent target

- **Target = any agent.** Config = `{model | endpoint, system_prompt, params}`. `submit(input)`
  = one LLM/endpoint call (chat) or sandboxed run (code). Built-in demo agents (a coder, a
  support bot) + BYO (pick an OpenRouter model + paste a system prompt; advanced: HTTP endpoint).
- **Human-friendly spec.** Plain-English task + failure conditions (+ optional hidden tests).
  An LLM "spec compiler" turns it into checkable obligations. Versioned (`agent_configs`,
  spec history).
- **Red = pure LLM** (no scipy): crafts adversarial inputs in natural language, adapts, names
  tactics, white-box.
- **Blue = pure LLM**: rewrites system prompt / adds guardrails (never retrains the vendor
  model); validates on held-out attacks.
- **Oracles, agent flavor:** judge-led (Opus reads output+spec), held-out (Opus-generated
  hidden checks), differential (different model answers, compare), metamorphic (rephrase →
  consistent), consistency/format. Reuse the aggregator.
- **Loop is co-evolutionary:** red→verify→blue→red for N rounds, ASR + detection per round.
- **Cost no object**, but the **public endpoint needs a budget cap** (per-run + global) before
  real Claude is enabled there.

## 6. Milestones & tasks  (bead IDs in brackets)

### Milestone A — Generic AGENT target: "bring any AI"  [`cr-mA`]
- `cr-a1` `AgentTarget` adapter (model/system-prompt → `submit`); built-in demo agents.
- `cr-a2` Human-friendly spec + LLM spec-compiler → obligations; `agent_configs` + spec versions.
- `cr-a3` BYO-agent path (pick OpenRouter model + system prompt; advanced: HTTP endpoint).
- `cr-a4` Wire the target into the loop/wiring/health; one end-to-end run against a demo agent.

### Milestone B — AI ATTACKER (red) for agents  [`cr-mB`]
- `cr-b1` `LLMAgentRed`: Claude crafts adversarial inputs to violate the spec; reasons + adapts.
- `cr-b2` Strategy catalog: name + distill tactics, reuse across runs → `/catalog`.
- `cr-b3` White-box red (scheme-aware prompt; tries to beat all checkers).
- `cr-b4` Full `llm_calls` logging (prompt/response/tokens/cost) → Inspect button.

### Milestone C — Checker panel (oracles) for agents  [`cr-mC`]
- `cr-c1` LLM judge generalized (reads agent output + obligations well).
- `cr-c2` Held-out oracle for agents (Opus generates hidden checks/tests from the spec).
- `cr-c3` Differential (a different model answers the same input; compare) + metamorphic
  (rephrase→consistent) + consistency/format checks.
- `cr-c4` Aggregator wired for the agent target; verdicts with 5 cards.

### Milestone D — AI DEFENDER (blue) + co-evolution  [`cr-mD`]
- `cr-d1` `LLMAgentBlue`: reads the catalog → proposes revised system prompt / guardrails →
  applies as a new `agent_configs` version (vendor model never retrained).
- `cr-d2` Held-out validation (re-test the patched agent on attacks defined up front).
- `cr-d3` Co-evolution loop: red→verify→blue→red for N rounds; ASR + detection per round.
- `cr-d4` `/coevolution` + `/blue/:patchId` endpoints.

### Milestone E — Self-serve Graphite-Meridian dashboard  [`cr-mE`]
- `cr-e1` Swap in the team's export (`~/GitHub Crucible Repository-2`) and serve it.
- `cr-e2` Self-serve Run Launcher (bring-an-agent form: model/prompt/spec) → POST /runs.
- `cr-e3` Wire all screens (live reasoning trace, verdict detail, catalog, blue patch review,
  co-evolution curves, white-box, health, dashboard, audit replayer, spec history, leaderboard,
  admin/debug) to live data.
- `cr-e4` Backends: deterministic replay+diff, spec-history, leaderboard JSONL, admin/debug.

### Milestone F — Trust score, report, cap, go-live  [`cr-mF`]
- `cr-f1` Headline trust score + honest metrics generalized beyond fraud.
- `cr-f2` Risk report (SR-11-7-style, generalized) + PDF.
- `cr-f3` Weakness corpus + leaderboard export.
- `cr-f4` Real-LLM cost meter + budget cap (per-run + global) — makes a public real-Claude
  run safe.
- `cr-f5` Turn ON real Claude red+blue+judge on the live service (behind the cap).
- `cr-f6` Demo runbook + DEPLOY-VERIFY on the VPS.

## 7. Honest residuals to carry forward

- Open-ended agent tasks lack ground truth → the judge + held-out generation carry more
  weight there; report that limitation.
- Real Claude on a public URL = real spend → `cr-f4` budget cap is a hard prerequisite for
  `cr-f5`.
- Fraud target stays as a demo; its blue retrain honestly does not generalize (keep that
  finding visible, don't hide it).

## 8. Resume instructions (for a fresh context)

1. Read this file + project memory (`crucible-redteam.md`).
2. `cd ~/crucible-rebuild && source .venv/bin/activate`; Postgres = docker `crucible-pg` on
   `127.0.0.1:55432`; live = systemd `crucible-integrity` (`sudo journalctl -u crucible-integrity`).
3. From the rig (`cd ~/gt/crucible`): `bd ready` → next task. Build → ruff + mypy --strict +
   `scripts/check_module_imports.py` + pytest must pass → commit (Conventional + `Assisted-by:
   Claude`) → `bd close`. Never fake metrics. Reuse the engine; do not rebuild.
4. Push is blocked until `gh auth refresh -h github.com -s workflow` (token lacks workflow scope).
