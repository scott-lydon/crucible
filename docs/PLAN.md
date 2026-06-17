# Crucible — Implementation Plan

Bead prefix **`cr`**. Beads are the unit of work polecats execute. Milestones are sequential; beads within a milestone parallelize where dependencies allow. **Build begins only after plan approval.**

---

## Build order (milestones)

```
M0 Scaffold & contracts ──▶ M1 Attack + oracle ──▶ M2 Gate + report ──▶ M3 Fix + eval ──▶ M4 Demo + package
                                    │                                         │
                          (the soul: does it find real bugs?)     (the proof: does the fix hold?)
```

---

## M0 — Scaffold & contracts (foundation)

| Bead | Title | Depends | Acceptance |
|---|---|---|---|
| **cr-1** | Repo scaffold | — | Python package, CLI entrypoint, config schema (incl. operator-owned attestation), `pytest`/`ruff`/`mypy` wired, CI green. |
| **cr-2** | Adapter interface + black-box adapter | cr-1 | `send(message)->response` over HTTP/callable; optional `system_prompt`/`tools`/`guardrails`/`repo_path`. Unit-tested against a stub. |
| **cr-3** | Sample vulnerable target + benign suite | cr-1 | A deliberately-leaky support-bot fixture (planted canary secret + a `refund` tool) and a set of benign prompts, runnable through the adapter. |

## M1 — Attack engine + oracles (the soul)

| Bead | Title | Depends | Acceptance |
|---|---|---|---|
| **cr-4** | Oracle framework + deterministic oracles | cr-2, cr-3 | Canary plant/detect, tool-call interception, guardrail-fired signal; each returns a typed proof. |
| **cr-5** | Attack engine core (hybrid runner) | cr-4 | Per-attack inner loop (deliver → oracle-check → iterate), narrated reasoning, multi-seed execution. |
| **cr-6** | Seed library — 4 v1 classes | cr-5 | Prompt-leak, secret-exfil, tool-abuse, jailbreak payloads adapted from garak/PyRIT/promptfoo; licenses recorded in `THIRD_PARTY.md` (see SOURCES). |
| **cr-7** | LLM judge (jailbreak only) | cr-5 | Judge graded as one measured signal; calibration test vs labeled examples. |
| **cr-8** | Strategy catalog | cr-5 | SQLite store; winning tactics persist and are reused across runs; proven by a repeat-run test. |
| **cr-9** | Profiler (grey-box) | cr-2 | Reads system prompt/tools/guardrails into a target model the attacker consumes. |

**M1 exit:** on cr-3's target, the engine finds ≥3 confirmed vulns across ≥2 classes, each with ground-truth proof.

## M2 — Gate + reporting

| Bead | Title | Depends | Acceptance |
|---|---|---|---|
| **cr-10** | Findings model + single gate | cr-5 | Typed `Finding`; gate presents findings + fix plan; `approve` vs `auto` setting honored. |
| **cr-11** | Report generator | cr-10 | Markdown + JSON; JSON is machine-consumable by a driving coding agent. |

## M3 — Fix engine + eval (the proof)

| Bead | Title | Depends | Acceptance |
|---|---|---|---|
| **cr-12** | Root-cause clustering + layered fix proposal | cr-10 | Findings cluster to vulnerabilities; fixer picks strongest available layer (prompt/guardrail/tool-perm); emits candidate diff. |
| **cr-13** | Sandbox apply + inner accept loop | cr-12, cr-3 | Apply to sandbox copy → seen attacks fail **and** benign preserved → accept/iterate/degrade. Over-refusal rejected. |
| **cr-14** | Eval engine (three-set + metrics) | cr-13 | Held-out mutator **firewalled from fixer**; reports held-out catch rate, generalization gap, utility delta, per-class, residual. |
| **cr-15** | Diff/branch application (never live) + approve/auto wiring | cr-13 | Fixes land as a diff/branch; `auto` applies to branch, `approve` waits. Reversible. |

**M3 exit:** after fix, held-out catch rate up materially, utility delta ≈ 0.

## M4 — Demo + packaging

| Bead | Title | Depends | Acceptance |
|---|---|---|---|
| **cr-16** | MCP server | cr-11, cr-15 | A coding agent drives the full loop via MCP in `auto` mode, no human in the loop. |
| **cr-17** | End-to-end demo scenario | cr-16 | One-command run on cr-3's target completes the loop in ≈10 min. |
| **cr-18** | OSS packaging | cr-11 | License, README quickstart, `THIRD_PARTY.md` complete, contributor docs, operator-owned safeguards verified. |

## Later (separate epic — out of v1 scope)

White-box/full-repo code fixes + PR · indirect-injection + guardrail-bypass classes · multi-turn / memory-poisoning / cost-DoS · dashboard web UI · run DB / account · hosted service.

---

## Gas Town kickoff (run after plan approval)

```bash
# 1. Create the GitHub repo and push this planning bundle (one-time)
#    gh repo create Julian-Stancioff/crucible --private --source=/home/ubuntu/crucible --push

# 2. Register the rig (prefix already implied; uses 'cr')
gt rig add crucible https://github.com/Julian-Stancioff/crucible.git
gt crew add julian --rig crucible

# 3. Seed the beads from this plan (one per row above), e.g.:
gt assign --rig crucible "cr-1: Repo scaffold" --crew julian
# ...repeat for cr-2 … cr-18, setting dependencies per the tables…

# 4. Optional: PRD/design review convoys before slinging build work
gt formula run mol-prd-review --problem "Crucible AI red-team — see docs/PRD.md"
gt formula run design --problem "Crucible architecture — see docs/DESIGN.md"

# 5. Start building (minimal/crew mode — reliable; the autonomous polecat daemon was flaky on prior builds)
gt sling cr-1 --rig crucible
```

> Reminder: confirm the **team-direction open question** (PRD §9.1) before kickoff — this plan builds the OSS dev-tool pivot, not the team's original fraud-model/sealed-spec scope.
