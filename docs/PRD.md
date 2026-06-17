# Crucible — Product Requirements Document

**Status:** Draft for plan review · **Owner:** Julian · **Bead prefix:** `cr` · **Showcase:** live demo

---

## 1. Problem

As engineers ship more AI agents, the dominant risk shifts from *"is the code correct"* to *"can the agent be talked into doing the wrong thing."* Prompt injection, jailbreaks, secret leakage, and tricked tool calls are **behavioral** failures — they live in the model's response to adversarial input, not in the source — so ordinary tests and code scanners miss them. Today an engineer has no easy, repeatable way to adversarially test their **own** agent and then close the holes. Existing tools either scan code (SAST) or are research harnesses, not a developer loop.

## 2. Users & use

- **Primary user:** a software engineer testing an AI agent they own (chatbot, assistant, tool-using agent).
- **Two driver modes:** a human at a **CLI**, or a **coding agent** (e.g. Claude Code) calling Crucible as an **MCP tool**.
- **Posture:** open-source, local-first, bring-your-own model key.

## 3. Goals

- **G1** Find real behavioral vulnerabilities in an owned agent, each with **ground-truth proof**.
- **G2** Harden the agent — suggest or apply fixes — **without breaking normal behavior**.
- **G3** Prove the fix **generalizes** (held-out catch rate), not just memorizes the attacks found.
- **G4** Produce clear, **human- and machine-readable** reports.

## 4. Non-goals (v1)

- Not a code-quality / SAST scanner.
- Not for attacking third-party / unowned systems — **operator-owned only**.
- No model retraining (we fix the AI layer; we do not retrain a model).
- No hosted multi-tenant service (local-first in v1).

## 5. Product loop

```
Profile → Attack (autonomous, narrated) → ▮Gate (findings + fix plan; approve|auto) → Fix (diffs, never live) → Re-eval (held-out) → Report
```

The **only** stop is the gate, after attacking. It is addressed to whoever drives the tool: a human answers go/no-go; a coding agent answers via its own policy. One setting (`approve` vs `auto`) selects which.

## 6. Requirements — v1 / MVP

| # | Requirement |
|---|---|
| **R1 · Adapter** | Grey-box contract: a channel to the agent (endpoint/callable) + optional read access to system prompt, tool manifest, guardrail config. Black-box (channel only) as fallback. |
| **R2 · Attack engine** | Hybrid: seed payload library steered by an LLM that adapts to the target; narrates its reasoning; persists winning tactics to a strategy catalog. |
| **R3 · Attack classes (v1)** | System-prompt / instruction extraction, secret/PII exfiltration, tool/function abuse (all deterministic) + jailbreak (judge). |
| **R4 · Oracles** | Deterministic where possible — planted canaries, tool-call interception, guardrail-fired signal — plus one LLM judge for the jailbreak class only. |
| **R5 · Gate** | Present findings + proposed fix plan; `approve` (wait for go) vs `auto` (apply to branch). |
| **R6 · Fix engine** | Root-cause clustering → strongest available defense layer (prompt / guardrail / tool-perm) → candidate diff → sandbox-tested (seen attacks fail **and** benign preserved) → iterate or degrade gracefully → emit diff, never live. |
| **R7 · Eval** | Three sets — Seen (`S`), Held-out (`H`, firewalled from the fixer), Benign (`B`). Headline = **held-out catch rate**; also report generalization gap and utility delta. |
| **R8 · Report** | Markdown (human) + JSON (machine). |
| **R9 · Surfaces** | CLI + MCP server. |
| **R10 · Safety** | Operator-owned attestation in config; refuse arbitrary public targets; permissive OSS license; vendored corpora license-recorded. |

## 7. Success criteria

- On a deliberately-vulnerable sample target, Crucible finds **≥3 distinct confirmed vulnerabilities across ≥2 classes**, each with ground-truth proof.
- After fixing, **held-out catch rate improves materially** while **utility delta ≈ 0** (no over-refusal).
- A coding agent can drive the **entire loop via MCP** in `auto` mode with no human intervention.
- The end-to-end demo runs from one command in **≈10 minutes**.

## 8. Scope — later (post-v1)

White-box / full-repo code fixes + PR; indirect prompt injection + guardrail-bypass classes; multi-turn, memory-poisoning, cost/DoS attacks; a local dashboard web UI; run database / account; a hosted service; authorization-gated broader targeting.

## 9. Open questions (resolve in plan review)

1. **Team direction.** Is this the *team capstone* (align with the `scott-lydon/crucible` fraud-model/sealed-spec scope) or our **OSS dev-tool pivot**? This PRD assumes the dev-tool pivot. *(Unresolved — flagged repeatedly; needs a decision before kickoff.)*
2. **Repo host & name.** `github.com/Julian-Stancioff/crucible`?
3. **Default model + per-run token budget** for attacker and judge.
4. **Stack confirm:** Python core (assumed — see DESIGN).
