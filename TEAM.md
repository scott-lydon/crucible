# Crucible — for the team (test it in 2 minutes)

**What it is:** an automated AI red-team. Point it at an AI agent you own; it attacks the agent's
*behavior* (prompt injection, secret leakage, tool abuse, indirect injection, jailbreaks), **proves**
each break with a ground-truth check, **fixes** it with a verified guardrail, and **proves the fix
held** on attacks it never saw. Runs from the CLI or as an MCP tool. This branch (`julian/devtool-mvp`)
is the developer-tool version; `main` is the original research proposal.

## 0. Easiest — open the hosted demo (no install, no key)

**→ https://crucible-51-81-34-160.nip.io**

Paste a system prompt (or use the built-in sample bot), hit **Attack it**, and watch Crucible break
it and produce a report. The sample bot is free and instant; real models cost a few cents (covered by
my key for now). That's the whole tool in a browser.

## 1. Try it offline on your machine — no API key, ~30 seconds

```bash
git clone -b julian/devtool-mvp https://github.com/scott-lydon/crucible
cd crucible
python -m venv .venv && . .venv/bin/activate     # or: uv venv && . .venv/bin/activate
pip install -e .
crucible demo
```

You'll watch it break a built-in vulnerable support bot across all 5 attack classes, propose fixes,
and re-test. Open the report: **`runs/report.html`** (also `report.md`, `report.json`, `run.jsonl`).

## 2. Test a real model — needs an OpenRouter (or Anthropic) key

```bash
pip install -e ".[anthropic]"          # optional
export OPENROUTER_API_KEY=sk-or-...
# attack a real LLM agent (canary planted in its system prompt), verified by the canary oracle:
crucible run --target llm:meta-llama/llama-3.1-8b-instruct \
             --llm openrouter --model anthropic/claude-3.5-haiku \
             --i-own-this-target --yes --max-attacks 6
# add --search for adaptive (best-of-N/TAP) attacks, --multi-turn for crescendo
```

A run costs **cents** (the client tracks and caps cost). Try `--target llm-tools:<model>` for a real
**tool-calling** agent (it'll try to trick it into an over-limit refund).

## 3. Test YOUR OWN agent

- **Your API:** `crucible run --target https://yourapp/chat --i-own-this-target` (configure the
  request/response shape via `--config`; auth via `CRUCIBLE_TARGET_AUTH`).
- **A website chatbot (no API):** `pip install -e ".[browser]"` then
  `crucible run --target browser:https://yourbot --i-own-this-target`.
- **Just want to harden a prompt?** Tell us the model + system prompt; we stand it up as a target.

## 4. What you'll see

A report with: confirmed findings (each with a ground-truth proof), the proposed/applied fix per
vulnerability, a **before/after held-out catch rate**, a **sealed-set** number (audits for
overfitting), a **fix-durability** verdict (re-attacks the fix), and per-class breakdowns — plus a
JSONL audit trail. Also: `crucible verify` (recall + false-positive rate on known targets) and
`crucible calibrate-judge`.

## 5. What it catches — and the honest limits (read this)

- **It reliably finds + fixes** secret leakage, tool abuse, prompt extraction, and indirect injection
  in the kind of agents people actually deploy (open / fine-tuned / custom-prompt models). Live, it
  found and fixed real bugs in **Llama-3.1-8B** (secret leak, `refund(5000)`).
- **Frontier-aligned models (Claude, GPT-4o) resist** system-prompt-secret extraction even under our
  strongest techniques + adaptive search — and Crucible **reports that correctly (no false
  positives)**. That's the truth about your agent, not a tool miss. See `docs/ISSUES.md §H/§J`.
- The **proof is deterministic** where it matters (canaries, tool-call interception); only jailbreak
  uses an LLM judge, which we calibrate.

## Status
Working MVP+: 36 tests, CI, ruff-clean; 5 attack classes; 5 ways to reach a target (sim / browser /
HTTP / real LLM / real LLM+tools); adaptive search + multi-turn; HTML/JSON/Markdown/JSONL reports.
Deferred stretch in `ROADMAP.md`. Honest limits in `docs/ISSUES.md`.

**The decision for the team:** this is a *pivot* from the original proposal toward a shippable
developer tool. Review the branch, run the demo, and decide: adopt it, keep the original direction,
or run both.
