# Crucible — Issues, Feasibility & Usability (read this before believing the demo)

This documents what is **genuinely real**, what is **simulated**, the problems hit
during the build, and the **honest feasibility & usability limits**. The headline
demo numbers (100% vs 38% held-out catch) are **real for the built-in simulation
and illustrate the mechanism — they are NOT empirical claims about real agents.**

---

## A. What is genuinely real and tested (24 tests; real browser E2E + live-LLM verified)

- The full pipeline runs end-to-end: profile → attack → gate → fix → held-out re-eval → report.
- **Deterministic oracles** (planted-canary leak detection, tool-call interception) are real ground truth — no model opinion involved.
- The fix engine's **structural-over-prompt preference**, **sandbox accept-loop**, and
  **over-refusal (benign) gate** are real and *demonstrably* produce better generalization
  (structural 100% vs prompt-only 38% held-out catch on the sample target).
- The **held-out firewall** (the fix engine never receives the held-out set `H`) is a real
  information-flow separation in the code, not a promise.
- The **operator-owned safety gate** is enforced (refuses to run without attestation).
- CLI, JSON/Markdown reports, strategy catalog (SQLite, persists across runs), and a
  callable MCP-style stdio server all work.

## B. Build issues encountered

1. **No `ANTHROPIC_API_KEY` and no `anthropic` SDK** in the build environment → the tool was
   designed to run **offline/deterministically** with the LLM as a pluggable interface. The
   real-LLM path (`--llm anthropic`) is wired but **was never exercised here** (no key).
2. **Python 3.14** in the environment → kept the core **stdlib-only** to avoid dependency
   compatibility risk. Good for reliability; means no heavyweight ML/NLP deps yet.
3. **Gas Town**: the autonomous polecat daemon is flaky (per project memory), so the rig +
   crew + 18 beads were created, but the build was done **directly** rather than dispatched.
   `bd` assigns hash-suffixed IDs (e.g. `cr-13g`), not sequential `cr-1`.
4. The upstream `.gitignore` didn't cover Python; replaced it so build artifacts don't commit.
5. The repo is a **teammate's** and encodes the *original* direction; this work is pushed as a
   **branch** (a pivot proposal), with the original README preserved at
   `docs/ORIGINAL_PROPOSAL.md`.

## C. Feasibility limits (the important, honest ones)

1. **The simulated target is the load-bearing simplification.** The offline demo rests on
   `SampleTarget`, a deterministic model of a *gullible* LLM. Real LLMs are stochastic,
   understand more nuance, and fail in ways the sim doesn't model. On a real target, held-out
   catch rates will be **lower and noisier**.
2. **The attacker is only as good as its LLM.** Offline it's a curated seed library + 4
   deterministic mutators — it finds *known* vulnerability shapes but won't *discover* novel
   ones. The "LLM as adaptive search engine" that makes Crucible interesting **needs a real
   LLM** (interface present, untested here). Without it, this is closer to a parameterized
   scanner than an adaptive red-teamer.
3. **The oracle problem is only contained, not solved.** Canaries and tool-interception are
   robust ground truth. But the highest-value real attacks (subtle policy violations,
   harmful-but-plausible content, multi-turn manipulation) have **no ground-truth oracle** and
   fall back to an **LLM judge** that shares the producer's blind spots — the weakest link.
   We made 5 of 6 v1 classes deterministic precisely to minimize reliance on it.
4. **"Fix it itself" requires a reconstructable target.** Re-evaluation builds a *modified
   clone* (`clone_with_config`). That works grey/white-box (Crucible controls the AI-layer
   config). For a real **black-box** agent, Crucible can only **suggest** — it can't
   apply-and-verify, because it can't instantiate a patched copy. The headline "auto-fix +
   prove it" fully holds only when the operator exposes a "rebuild with this config" seam.
5. **Held-out generalization is a proxy, not a guarantee.** It measures robustness to variants
   *we* generate; a fix can still fail against techniques neither the attacker nor the held-out
   generator covers. The number is honest about what it tests; it **cannot certify safety**.
6. **MCP server is minimal, not protocol-complete.** Callable (initialize / tools-list /
   tools-call over newline-delimited JSON-RPC) but **not validated against the official MCP
   spec/client**. Production should use the official `mcp` package.
7. **The HTTP adapter is a stub.** It assumes one request/response JSON shape; real agents vary
   (auth, streaming, history, tool schemas). Each real target type needs a real adapter.

## D. Usability issues

1. **Grey-box config burden.** To get value beyond black-box, the engineer must expose the
   system prompt + tools + guardrails **and** a way to rebuild the agent with a patched config.
   Many teams lack a clean seam for that.
2. **Approve-mode is non-interactive-hostile.** Under no TTY (CI / agent), `approve` defaults to
   *not* proceeding unless `--yes`. Safe, but a driving agent must know to pass it.
3. **Fixes are config patches, not applyable code PRs yet.** Guardrail/tool "diffs" are
   readable summaries. White-box **code-level diffs + branch/PR** (the L2 promise) are not
   implemented.
4. **No cost/latency controls for the real-LLM path.** seeds × attacks × LLM calls can get
   expensive; no caching/budgeting yet.
5. **Held-out reproducibility** depends on deterministic mutators; with a real LLM mutator the
   set varies per run and no generation seed is logged yet.

## F. Browser integration (added 2026-06-18) — verified vs not

**Verified, tested, working:**
- `BrowserAdapter` drives real headless Chromium (Playwright) against a web chat UI: types the
  attack, reads the bot reply **and tool calls from the rendered DOM**.
- A built-in web test-env (`crucible.testenv`) serves the vulnerable AcmeBot over HTTP with a
  chat widget, grey-box config endpoint, and patched-clone support.
- `crucible browser-demo` runs the **entire** loop (attack → fix → held-out re-eval) through the
  browser: 30 findings, 4 structural fixes, 100% held-out catch — **no API key**.
- 2 browser tests (auto-skip if chromium is absent).

**Environment note:** this host is Ubuntu 26.04, which Playwright's chromium *download* doesn't
recognize. The adapter auto-detects the already-cached Chromium binary (or `$CRUCIBLE_CHROME`)
and launches with `--no-sandbox`.

**NOT verified (honest):**
- The **browser-use Agent autonomous-navigation** path (LLM figures out an unknown UI) is wired
  as a dependency + documented, but **needs an API key and was not exercised** — do not treat it
  as working. The tested browser path uses Playwright directly.
- The DOM "side-effect oracle" is only as independent as the app's rendering; in the test-env the
  UI renders from the same JSON, so it demonstrates the mechanism but isn't yet a fully
  independent signal on a real app.

## G. Evaluated and declined: ruflo (claude-flow)

Assessed `github.com/ruvnet/ruflo` for inclusion. **Declined.** It is a 1865-file Node/TypeScript
multi-agent orchestration framework (0 Python) — a peer to Gas Town, not a security component. Its
`ruflo-aidefence` plugin is Claude-Code-plugin prose (commands + an agent persona), not an
extractable, testable attack corpus or library; its concrete payloads are generic ones Crucible
already has. Integrating it would add a heavyweight Node dependency to a deliberately stdlib-only
Python tool and duplicate Gas Town, with no testable security gain. The earmarked
garak/PyRIT/promptfoo sources (`docs/SOURCES.md`) are the right Python-native, license-clean path.

## H. Live-model findings (OpenRouter, 2026-06-18) — the empirical part

Exercised the real-LLM paths against live models via OpenRouter (~$0.02 total, budget-capped).
These are findings the deterministic/mock paths could not have surfaced:

1. **Aligned models resist the public-payload library.** System-prompt-secret extraction, 16
   public injection payloads each:

   | Model | leaks / 16 |
   |---|---|
   | Claude 3.5 Haiku | 0 |
   | GPT-4o-mini | 0 |
   | **Llama-3.1-8B** | **8** |
   | Mistral-7B, Gemini-Flash-1.5 | errored on the gateway ($0 — not a valid measurement) |

   A static, public library cannot crack a frontier-aligned model — empirical evidence that a real
   product needs an **adaptive LLM attacker** + harder corpora (garak/PyRIT) + multi-turn.

2. **The full real loop works on a leaky real model.** On Llama-3.1-8B: baseline 25% of held-out
   attacks landed → after the **output-redaction guardrail-wrapper** fix, **100% held-out catch,
   utility +0%** — a real fix proven on a real model via the deterministic canary oracle.

3. **Judge-model choice matters enormously.** Same labeled set: GPT-4o-mini 100% precision/recall;
   Claude 3.5 Haiku 57%. The judge is the weak link; `crucible calibrate-judge` makes it a number.

4. **Safety-trained models refuse the attacker role.** Asked to "produce jailbreak prompts," Claude
   Haiku refused — and the refusal was initially mistaken for an attack. Fixed with refusal
   filtering + authorized-testing framing; some classes likely need a less-aligned attacker model.

5. **Adaptive rewrite works.** Claude Haiku (as attacker) bypassed a "secret token" blocklist by
   switching to "authorization token" — the iterate-on-block loop adapting past a defense.

**New limitation noted:** `LLMAgentTarget` swallows API errors as empty (non-leaking) replies, so a
gateway error silently reads as "robust" (see Mistral/Gemini above). A real benchmark must
distinguish refusal/safe from errored.

## E. Honest bottom line

The **machine** is real, tested, and demonstrates the core thesis (deterministic proof +
held-out firewall + structural-over-prompt fixing + over-refusal gate). The **intelligence**
(adaptive LLM attacker, LLM judge, real-target adapters, code-level fixes) is interface-ready
but **not yet proven on real agents**. Crucible today is a *credible skeleton and a working
demo of the idea*, not a battle-tested product. The next real milestone is exercising the
`--llm anthropic` path against one real, owned agent and reporting how the numbers move.
