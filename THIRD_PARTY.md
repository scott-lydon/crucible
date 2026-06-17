# Third-party sources

The v1 attack corpus is **hand-written and original** (`src/crucible/attacks/library.py`) —
no third-party payloads are vendored yet, so there are currently **no inbound license
obligations** beyond this project's own MIT license.

## Planned integrations (not yet vendored)

When the roadmap pulls in external corpora, each MUST be recorded here with its license,
verified at integration time (see `docs/SOURCES.md`):

| Source | License (verify at integration) | Use |
|---|---|---|
| garak (NVIDIA) | Apache-2.0 | probe library |
| PyRIT (Microsoft) | MIT | payload sets / orchestration |
| promptfoo | MIT | eval harness / red-team plugins |
| OWASP LLM Top 10 / ATLAS | docs (attribution) | threat taxonomy |
| AgentDojo / InjecAgent | check per-repo | agent injection benchmarks |
| JailbreakBench / HarmBench / AdvBench | research / restrictive — **quarantined** | jailbreak corpora |

Harmful-content datasets are quarantined: do not vendor without a clear, recorded license basis.
