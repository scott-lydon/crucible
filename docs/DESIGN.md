# Crucible — Technical Design

Condensed from the canonical design (`~/crucible_design.md`). This is the build-facing architecture.

---

## 1. System layers

| Layer | Responsibility |
|---|---|
| **Adapter** | The progressive contract between Crucible and the target (black → grey → white). |
| **Profiler** | Reads whatever the adapter exposes; builds a target model. |
| **Attack engine** | Hybrid seed-library + LLM, adaptive, narrated, with a persistent strategy catalog. |
| **Oracle / verification** | Proves each attack succeeded — deterministically wherever possible. |
| **Gate** | The single human/agent decision point: findings + fix plan, `approve` vs `auto`. |
| **Fix engine** | Generates reviewable, AI-layer-scoped fixes; sandbox-tested before emit. |
| **Eval engine** | Three-set (Seen / Held-out / Benign) before-after measurement. |
| **Reporting** | Markdown + JSON; the honest dashboard of metrics. |
| **Surface** | CLI + MCP server. |

## 2. Adapter — progressive access

- **L0 · Black-box** — endpoint/callable only (message in → response out). Always works; weakest attacks; *suggest-only* fixes.
- **L1 · Grey-box (v1 default)** — channel **+** read access to system prompt, tool manifest, guardrail config. Sharp attacks; concrete config fixes.
- **L2 · White-box (later)** — **+** full repo. Real code fixes; the "attacker knows the whole scheme and still gets through" mode (the natural mode when a coding agent drives).

The adapter is one interface (`send(message) -> response`, plus optional `system_prompt`, `tools`, `guardrails`, `repo_path`). The more populated, the more capable the run.

## 3. Attack engine (hybrid + strategy catalog)

Per attack, an inner loop mirroring a real attacker:

```
profile → pull tactic from seed library/catalog → mutate/adapt to target → deliver via adapter → oracle-check → iterate or escalate → distill win to catalog
```

- **Seed library** (sourced — see `SOURCES.md`) gives reproducibility; it doubles as the regression corpus.
- **LLM steering** mutates and adapts to the live target; narrates "here's the attack, here's why."
- **Strategy catalog** (SQLite) persists winning tactics, reused/compounded across runs.
- **v1 classes:** prompt/instruction extraction, secret/PII exfiltration, tool/function abuse, jailbreak.

## 4. Oracle / verification — proof, not vibes

| Attack class | Proof of success |
|---|---|
| System-prompt / instruction extraction | **canary** planted in prompt → string-match if leaked |
| Secret / PII exfiltration | planted **canary secret** → deterministic leak detection |
| Tool / function abuse | **intercept the tool call** → fired? with what args? |
| Indirect prompt injection *(later)* | did it follow the injected (canary) instruction? |
| Guardrail bypass *(later)* | did the guardrail fire or not? |
| Jailbreak / policy bypass | **LLM-judge** graded (the only fuzzy class) |

Run each attack across a few seeds; count a hole as open if it succeeds in **any** seed (attacker-favorable).

## 5. Fix engine — a loop graded on security AND utility

1. **Cluster by root cause** — many payloads → one vulnerability → one fix.
2. **Pick the strongest available defense layer** (prefer structural over persuasion):
   - A · system-prompt hardening (weakest — a prompt can be talked around)
   - B · guardrails (input/output classifiers)
   - C · tool/capability controls (**strongest for tool-abuse — removes the capability**)
   - D · code boundary (white-box only)
3. **Propose a minimal layered diff.** The fixer sees **only the seen attacks** — firewalled from `H`.
4. **Inner accept/iterate loop:** apply to a **sandboxed copy** → re-run **seen attacks** (must fail) → re-run **benign suite** (must NOT break) → accept, else feed back and iterate up to N rounds; if neither converges, **degrade gracefully** (best suggestion + why it's hard).
5. **Emit as diff / branch — never live.** At white-box, open a PR.

> Without step 4's benign check the engine has a degenerate win: refuse everything → "100% secure" → product destroyed. **Over-refusal is the #1 failure mode** — graded every round.

## 6. Eval engine — three sets, one firewall

- **Seen (`S`)** — attacks that worked; fixer sees these. Re-run → ~0 success (fix *engages*).
- **Held-out (`H`)** — fresh variants + novel same-class attacks from a mutator **information-flow-firewalled from the fixer** (separate component; ideally different model family). Operators: paraphrase, encode/obfuscate, translate, role-play-wrap, multi-turn split, position-shift. **Held-out catch rate = headline.**
- **Benign (`B`)** — legitimate prompts (engineer-supplied if available, else generated). Before/after → utility delta.

**Metrics:** held-out catch rate (headline) · generalization gap (`S` − `H`; large = memorized) · utility delta · per-class breakdown · residual (held-out attacks still getting through → optional next round / co-evolution).

## 7. Orchestration

Two distinct orchestrations — do not conflate:

- **Build-time:** **Gas Town** (this rig) orchestrates the *construction* — mayor + polecats executing `cr-*` beads.
- **Run-time (the product):** Crucible ships its **own self-contained orchestrator** (a lightweight mayor-+-subagents fan-out: one worker per target/attack class) so an OSS user needs no proprietary dependency. *(Confirm in plan review — PRD open question, and consistent with "anyone can use it.")*

## 8. Stack (proposed)

- **Core:** Python 3.12+ (matches garak/PyRIT/promptfoo ecosystem).
- **Persistence:** SQLite — strategy catalog + run history.
- **LLM:** provider-pluggable; default Claude (`claude-opus-4-8` for strategy/planning, `claude-sonnet-4-6` for high-volume generation); BYO API key.
- **Surfaces:** CLI (core) + MCP server (coding-agent driver). Optional later: FastAPI + light JS dashboard.
- **Reports:** Markdown + JSON.

## 9. Core data objects

- **`Target`** — adapter handle + profile (system prompt, tools, guardrails, repo?).
- **`Attack`** — class, payload/template, mutation lineage, the oracle it carries.
- **`Finding`** — attack + target response + **proof** (oracle signal) + severity + implicated surface.
- **`FixCandidate`** — root-cause, layer, diff, sandbox result (seen-pass + benign-pass).
- **`EvalResult`** — per-set scores + metrics.
- **`Report`** — findings + fixes + before/after, rendered MD/JSON.
