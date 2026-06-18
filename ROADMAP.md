# Roadmap (deferred stretch items)

The v1 developer-tool MVP is complete (see `CHANGELOG.md`). The items below are intentionally
deferred — each needs something not cleanly testable in the current environment, so rather than
ship unverified code we document the design. Their Gas Town beads stay **open**.

## F1 — White-box code-level fixes + branch/PR (L2 access)
Today fixes are prompt/config patches + **guardrail wrappers** (the deployable, verifiable layer —
e.g. output redaction, tool-permission checks proven on real models). True L2 means editing the
target's *source* (the guardrail function, input sanitizer, tool-permission check) and opening a
branch/PR. Needs: a repo-access adapter (`repo_path`), an LLM code-patch generator (unified diffs
against real files), a sandbox that rebuilds the agent from patched code, and `gh`/git PR creation.
Deferred because verifying it honestly requires a real codebase target.

## F2 — Protocol-complete MCP server
`mcp_server.py` speaks newline-delimited JSON-RPC (initialize / tools-list / tools-call) and is
callable, but is not validated against the official MCP spec/client. Replace with the official
`mcp` package (stdio transport, capability negotiation, resources/prompts), expose the
`verify` / `calibrate-judge` tools, and test against a real MCP client.

## browser-use autonomous navigation (`cr-bs4`)
The tested browser path uses Playwright directly (deterministic). browser-use's **Agent** (LLM-driven
navigation of unknown chat UIs) is installed and wired as a dependency but unexercised. Needs: the
browser-use Agent configured with an OpenAI-compatible client (OpenRouter `base_url`), a goal
template, and a real browser run to verify. A power-mode enhancement, not core.

## Other strong candidates (the real lever vs aligned models)
- Vendored **garak / PyRIT** corpora behind the existing library interface (the public payloads
  here can't crack frontier-aligned models — see `docs/ISSUES.md §H`).
- Tree-of-attacks / many-turn search; translation & token-smuggling chains.
- Memory-poisoning and cost/DoS attack classes.
- Per-attack statistical distributions (run all seeds, report success-rate not just any-seed).
- Hosted dashboard + run database/account.
