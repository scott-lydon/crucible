# The Crucible Goal Loop

The repeatable cycle we iterate to drive Crucible toward done. Self-contained: an agent (or the team) can pick this up and run it without further context.

**North star:** each iteration moves Crucible measurably closer to satisfying **`tasks.md`** (the slices) and **`acceptance-tests.md`** (the user stories), built to **`coding-practices.md`** and **`ARCHITECTURE.md`** — *honestly* (no fake data/metrics), *hexagonally* (the harness never imports `examples/`), *self-hostable* (Docker + Postgres-in-a-container, no external accounts), and *nothing-mocked in the demo path*.

## One iteration

1. **SELECT** — take the next item from the backlog (respect dependencies). One slice / user-story at a time.
2. **DEFINE-DONE** — write the item's **`vouch` criteria** (from `tasks.md`) + the **acceptance-test user story** it satisfies. If the docs are silent or contradictory, surface it and reconcile *before* building.
3. **BUILD** — dispatch a fresh **Opus** subagent (Ruflo-coordinated): TDD, hexagonal, fail-loud, **no fake data**, bounded LLM cost (mock in tests + one gated live call + per-run budgets).
4. **VOUCH (verify)** — gates green: `python scripts/check_module_imports.py` · `ruff check .` · `mypy --strict .` · `pytest` (fast on in-memory SQLite) — **plus** the item's acceptance test passes, the demo path stays real, and the suite's real-LLM-call count stays bounded. Drive runtime changes at the surface (run the app/endpoint), don't just trust tests.
5. **REVIEW** — adversarial **Opus** review against the done-criteria + the honesty/architecture bar → dispatch a fix subagent for Critical/Important findings → re-review until clean.
6. **LAND** — commit on `feat/critical-path` (`Assisted-by: Claude`, **never `main`**, explicit `git add` paths, no `Co-Authored-By`); tick the `tasks.md` box; append one line to `.superpowers/sdd/progress.md`.
7. **REPEAT.**

## Guardrails (true every iteration, non-negotiable)

- Never commit to `main`; teammate PRs stay open (local merges only).
- No fake data or metrics; partial/honest results are labeled as such.
- Hexagonal boundary machine-enforced (`scripts/check_module_imports.py`): `modules/` + `orchestrator/` never import `examples/`; only `orchestrator/wiring.py` (composition root) wires a concrete victim.
- Self-hostable: no new external-account dependency; managed services (Modal, cloud DB) are optional adapters behind a port, never requirements.
- LLM tiering per `coding-practices.md §1`: Sonnet 4.6 on the inner red/blue loops; Opus 4.8 on the judge oracle + the white-box self-test pass; the documented blue-code-engineer Opus deviation stands. Build-time subagents run on Opus.
- Bounded LLM cost: mock providers in tests, one gated single live call per provider, per-run call budgets.
- Gates green before landing.

## Backlog (iteration order)

1. **Seal core-bet** (US-9 / slice-4) — producer cannot reach the verification store; the Seal Probe (run inside the sandbox) must fail to reach Postgres, the sandbox host/control plane, and the verification bucket. Faithful now via Postgres-as-a-service + Docker `--network none`.
2. **White-box red = oracle-scheme** (US-14 / slice-12) — the red agent's prompt is given the *verifiers'* protocol descriptions; the dashboard reports black-box vs white-box catch rate side by side + the gap. (Note: this is white-box on the *oracles*, not on the target's code.)
3. **Measure pillar + our dashboard** (US-2/8/10/11/12/13, slices 15-18) — SSE stream, `/health`, `/metrics` five tiles ("Not yet measured" empty-state), `/corpus` export, SR 11-7 report, halt-cert banner + 409; the React dashboard built against the Claude Design mockups in `frontend/`.
4. **code-agent 2nd target** (slice-3) — validates target-agnosticism on a genuinely different victim.
5. **Housekeeping** — Alembic migrations; `tasks.md` staleness (`modules/targets`→`examples/targets`, menu-blue→code-engineer, white-box wording); add a Sparkov blind-spot invariant (e.g. night-hour) so property-fuzz bites the real detector.

## State pointers

- Working branch: `feat/critical-path` (a full-vertical prototype; teammate prototypes converge later — minimize edits to shared docs).
- Durable progress ledger: `.superpowers/sdd/progress.md`.
- Coordination: Ruflo swarm (coordination/memory) + Claude Code Agent tool (execution) + adversarial Opus review per item.
