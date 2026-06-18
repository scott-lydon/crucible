# Crucible — Attack-Corpus Sourcing & License Posture

We do **not** invent the attack corpus from scratch. Crucible stands on established, mostly-permissive sources. This file is the build crew's reference for what to vendor and under what terms.

> **Build-time task (bead `cr-6` / `cr-18`):** before vendoring anything, verify the *current* license and version of each source and record it in `THIRD_PARTY.md`. The notes below are the starting map, not a license guarantee — re-check.

## Threat taxonomy (the "what to test for" backbone)

- **OWASP Top 10 for LLM Applications** — canonical risk list; maps ~1:1 to our attack classes. Use for naming/structure in reports.
- **OWASP agentic-AI threat guidance** — tool-abuse / multi-step agent attacks.
- **MITRE ATLAS** — adversarial-ML technique knowledge base; shared vocabulary for findings.

## Seed payloads / probes (the library half of the hybrid attacker)

- **garak** (NVIDIA, Apache-2.0) — LLM vulnerability scanner with a large probe library. Closest existing analog; permissive.
- **PyRIT** (Microsoft, MIT) — red-team orchestration + payload sets.
- **promptfoo** (MIT) — red-team plugins **and** an eval harness; candidate basis for the before/after eval runner.

## Agent-specific injection (tool abuse / indirect injection)

- **AgentDojo**, **InjecAgent** — benchmarks for tricking tool-using agents via poisoned tool results. Feed the `tool-abuse` and (later) `indirect-injection` classes.

## Jailbreak corpora (the one fuzzy class)

- **JailbreakBench / HarmBench / AdvBench** — carry **harmful content** and **research-oriented / restrictive terms**. Use sparingly, if at all; prefer the permissive sources above. Do not vendor harmful content into an OSS repo without a clear, recorded license basis.

## License posture

- Target project license: **permissive (MIT or Apache-2.0)** to match the foundation.
- Permissive spine to rely on: **garak (Apache-2.0) + PyRIT (MIT) + promptfoo (MIT) + OWASP/ATLAS taxonomy.**
- Record every inbound source + license in `THIRD_PARTY.md`. Treat jailbreak/harmful datasets as quarantined unless cleared.

## Responsible corpus posture (DECIDED — 2026-06-18)

Crucible's goals are **benign**: extract a *planted canary* the operator owns, exceed a refund
limit, reveal a system prompt, or follow an injected instruction. None require harmful content.
So we **ship attack *techniques/structures*, not harmful-content payloads.** We evaluated the
recommended corpora and decided:

| Source | License | Decision |
|---|---|---|
| JailbreakBench (JBB-Behaviors + artifacts) | MIT | Techniques (TAP, search, role-play) **adopted**; harmful behavior prompts **not vendored** |
| HarmBench (400 behaviors) | MIT | Multilingual/encoding *techniques* adopted; harmful prompts **not vendored** |
| InjecAgent (1,054 cases) | Apache-2.0 | Indirect-injection *patterns* adopted; reference for the class |
| garak / PyRIT / promptfoo | Apache-2.0 / MIT / MIT | Permissive; usable as optional integrations |

Implemented techniques (against benign goals): policy-puppetry, persona/role-play, hypothetical,
dev-mode, encoding (base64/leetspeak/rot13), translation-frame, payload-split, many-shot, multi-turn
crescendo, and **best-of-N / TAP-style adaptive search**.

**BYO corpus:** advanced users may plug their own payloads via `--payloads <file>` (`{class: [str]}`),
at their own risk and license responsibility. We ship **no harmful content** in this repo.
