# Changelog

All notable changes to this branch. Format loosely follows Keep a Changelog.

## [0.1.0] — unreleased (branch `julian/devtool-mvp`)

The developer-tool instantiation of Crucible: attack an AI agent you own, prove each break with a
ground-truth oracle, fix it, and prove the fix held on held-out attacks.

### Added
- **Core loop**: profile → attack → gate → fix → held-out re-eval → report (CLI + minimal MCP).
- **Attack classes**: prompt-extraction, secret-exfil, tool-abuse, jailbreak, **indirect injection**.
- **Attack engine**: curated corpus + mutators (roleplay, base64, suffix, payload-split, many-shot,
  leetspeak, paraphrase, polite, rot13), strategy catalog, **LLM-adaptive** variants + rewrite-on-
  block, and a **multi-turn (crescendo)** attacker.
- **Oracles**: deterministic canary, tool-call interception, guardrail-fired; LLM judge for jailbreak
  (with a **calibration harness**).
- **Fix engine**: root-cause clustering, structural-over-prompt layers, sandbox accept-loop with an
  over-refusal gate; **fix-durability audit** (re-attacks the fix).
- **Eval**: three-way split (seen / held-out / **sealed**), generalization gap, utility delta.
- **Adapters**: sample sim target, configurable HTTP, **Playwright browser** (UI chatbots),
  **real-LLM target** (`--target llm:<model>`) verified by the canary oracle.
- **LLM clients**: deterministic, scripted (tests), Anthropic, **OpenRouter** (cost-tracked,
  call-capped).
- **Reports**: Markdown + JSON + **self-contained HTML** + **JSONL audit trail**; cost + timing.
- **Verification**: `crucible verify` (ground-truth recall / false-positive rate).
- **Config**: `crucible init` + `crucible run --config crucible.json`; `--max-attacks` cost cap.
- **Hosted demo**: `crucible.webapp_demo` (stdlib web app) — paste a system prompt, attack a real
  model or the offline bot, get the HTML report. Deployed at crucible-51-81-34-160.nip.io.
- **Integrations**: `py:module:function` target (wrap any callable / LangChain / OpenAI SDK);
  `--fail-on-findings` CI gate; `fixes.patch` export; configurable HTTP adapter.
- **Hardened attacks**: policy-puppetry / hypothetical / dev-mode / translation-frame mutators +
  best-of-N / TAP-style adaptive search (`--search`); BYO corpus via `--payloads`.
- Safety: operator-owned attestation enforced; 32 tests + 2 gated live tests; CI; ruff-clean.

### Live findings (OpenRouter)
- Public payloads leak Llama-3.1-8B 8/16; Claude-3.5-Haiku / GPT-4o-mini 0/16.
- Full real loop on Llama-3.1-8B: 25% held-out baseline → 100% after the redaction fix.
- Multi-turn crescendo: aligned models held; canary oracle avoided a hallucinated-secret false positive.
- Judge variance: GPT-4o-mini 100% vs Claude-3.5-Haiku 57% on the same labeled set.

See `docs/ISSUES.md` for honest limits.
