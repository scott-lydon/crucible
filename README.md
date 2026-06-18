# Crucible

**A red-team that breaks your own AI agent, then helps you harden it — and proves the fix actually held.**

> **Branch note.** This branch (`julian/devtool-mvp`) proposes a *developer-tool* instantiation of Crucible: instead of the fraud-model / sealed-spec research platform in the original proposal (preserved at [`docs/ORIGINAL_PROPOSAL.md`](docs/ORIGINAL_PROPOSAL.md) and `website/`), it ships a **working tool** that attacks the *AI behavior* of agents you own. Same spine (attack → verify → harden → re-eval), different organism.

Point Crucible at an AI agent **you own**. It adversarially probes the agent's *behavior* — prompt injection, jailbreaks, leaked secrets, tricked tool calls — proves each break with a **ground-truth signal**, proposes fixes as **reviewable diffs (never applied live)**, and re-tests against attacks it **never saw** to prove the fix generalized instead of memorizing the test.

It runs from a CLI or is driven by a coding agent over MCP. **The core is stdlib-only and runs fully offline** against a built-in simulated target — no API key required.

```
Profile → Attack (autonomous, narrated) → ▮Gate (findings + fix plan) → Fix (diffs, never live) → Re-eval (held-out) → Report
```

## Quickstart

```bash
uv venv && . .venv/bin/activate
uv pip install -e ".[dev]"

crucible demo                 # full loop on the built-in vulnerable sample agent
pytest -q                     # 16 tests

uv pip install -e ".[browser]"   # optional: browser support (playwright + browser-use)
crucible browser-demo            # same loop, driven through a REAL headless browser
```

Against your own target:

```bash
crucible run --target http://localhost:8080/chat --i-own-this-target --mode approve
```

The `--i-own-this-target` attestation is **required** — Crucible refuses to run without it.

## What a run produces

On the built-in sample agent (`crucible demo`):

| Metric | Structural fix | Prompt-only fix (`--prompt-only`) |
|---|---|---|
| Findings (ground-truth) | 30 across 4 classes | 30 across 4 classes |
| **Held-out catch rate** | **100%** | **38%** |
| Generalization gap | +0% | **+62%** (memorized!) |
| Utility delta (over-refusal) | +0% | +0% |

That contrast *is* the product: a prompt-only patch blocks the exact attacks it saw and quietly fails on fresh variants — and only the **held-out eval (which the fixer never sees)** reveals it. A structural fix (output guardrail / tool-permission control) generalizes.

Reports land in `runs/report.md` (human) and `runs/report.json` (machine, for a driving agent).

## Driving it from a coding agent (MCP)

```bash
python -m crucible.mcp_server      # newline-delimited JSON-RPC over stdio; tool: crucible_run
```

## Reaching UI-only chatbots (browser)

Many deployed assistants have no API — just a web chat widget. The **browser adapter**
(Playwright/Chromium) types attacks into the real UI and reads the bot reply **and tool
calls from the rendered DOM** (observing the actual side effect, not a trusted JSON field):

```bash
crucible run --target browser:http://localhost:8080 --i-own-this-target --mode approve
```

`crucible browser-demo` runs the entire loop through headless Chromium against a built-in
vulnerable web chatbot (`crucible.testenv`) — verified end-to-end with no API key. The
optional `browser-use` Agent (LLM-driven navigation of unknown UIs) is wired behind a
key-gated path; see `docs/ISSUES.md` for what is verified vs. not.

## Real LLMs (OpenRouter)

Run with a real model as the **attacker** (adaptive: generates + rewrites attacks) and/or as the
**target under test**:

```bash
export OPENROUTER_API_KEY=sk-or-...
crucible run --target llm:meta-llama/llama-3.1-8b-instruct \
             --llm openrouter --model anthropic/claude-3.5-haiku \
             --i-own-this-target --yes
```

`--target llm:<model>` makes the agent under test a real LLM (canary in its system prompt, verified
by the deterministic oracle). The client tracks per-call cost and hard-caps calls as a budget
guard. Add `--multi-turn` for a crescendo (multi-turn) attacker against an LLM target. Calibrate a
judge model with `crucible calibrate-judge`. Live findings (which real models leak, judge-model
variance, multi-turn robustness): **`docs/ISSUES.md §H–I`**.

## Attack classes

`prompt_extraction` · `secret_exfil` · `tool_abuse` · `indirect_injection` (deterministic oracles) · `jailbreak` (calibrated LLM judge).

## Commands

```bash
crucible run --target <spec> --i-own-this-target [--mode auto] [--multi-turn] [--max-attacks N]
crucible demo            # offline sample target        crucible browser-demo  # headless Chromium
crucible verify          # recall + false-positive rate crucible calibrate-judge
crucible init            # write a starter config        crucible run --config crucible.json
```

**Target specs:** `builtin:acmebot` · `browser:<url>` · `http(s)://<endpoint>` · `llm:<model>` (real LLM) · `llm-tools:<model>` (real LLM + a callable tool).
**Reports:** `report.md` · `report.json` · `report.html` · `run.jsonl` audit trail.

## Docs

[`docs/PRD.md`](docs/PRD.md) · [`docs/DESIGN.md`](docs/DESIGN.md) · [`docs/PLAN.md`](docs/PLAN.md) · [`docs/SOURCES.md`](docs/SOURCES.md) · **[`docs/ISSUES.md`](docs/ISSUES.md)** (feasibility & known limits).

## Status & honesty

This is a working **MVP**. The loop, oracles, fix engine, eval, CLI, and MCP server all run and are tested. The attack *intelligence* is currently a curated seed library + deterministic mutators (so it runs offline); a real LLM and the garak/PyRIT/promptfoo corpora plug in behind the existing interfaces. See [`docs/ISSUES.md`](docs/ISSUES.md) for exactly what is real, what is simulated, and the feasibility limits.

## License

MIT — see [`docs/SOURCES.md`](docs/SOURCES.md) for inbound-corpus license posture.
