# Constitution

The rules Crucible is built under. Violations are not "tech debt"; they are bugs that block merge.

This file is the first of the five foundational artifacts that govern the project. The other four (`spec.md`, `plan.md`, `tasks.md`, `QA_ADVERSARY.md`) reference rules defined here. If a downstream document contradicts a constitution rule, the constitution wins, and the downstream document is corrected.

## 1. Stack

- **Language:** Python 3.12. Forced by the machine-learning targets (LightGBM, scikit-learn, autoencoders), the Anthropic Software Development Kit (SDK), and `hypothesis` for property-based fuzzing. Swift cannot host these dependencies; no other language in the team's toolkit can either.
- **Web framework:** FastAPI. Single `POST /runs` endpoint streaming Server-Sent Events (SSE).
- **Persistence:** Postgres 16 (Supabase free tier in development, Render Postgres in production). SQLite is forbidden in code paths shared with the orchestrator; concurrent writes from two pillars will break it.
- **Object-relational mapping (ORM):** SQLAlchemy 2.x in async mode, with Alembic for migrations. No raw SQL outside `shared/persistence/`.
- **Producer sandbox:** a sandbox adapter behind a Protocol port. Default v1 adapter is a **local Docker/subprocess sandbox** (network-isolated, env-stripped, resource-limited); **Modal** is an optional production adapter. The producer container has no environment variables and no network access to Postgres or the verification artifact bucket.
- **Large language model (LLM) provider:** Anthropic Claude. Sonnet 4.6 on the inner red and blue loops; Opus 4.8 on the judge oracle and the white-box self-test pass. No other provider; no fallback to OpenAI or Google for "redundancy." Cross-family in the differential oracle is satisfied by the two model families (LightGBM versus IsolationForest for fraud; Sonnet versus Haiku for code), not by mixing vendors.
  - **Documented deviation (operator-approved, 2026-06-24): Opus 4.8 on the blue code-engineering loop.** The blue maker is no longer a feature-menu picker; it is a genuine code engineer that REASONS from the raw data schema to a hypothesis and WRITES a feature-engineering transform (Python source run in the producer sandbox). Code generation is held to the higher reasoning tier, so the blue maker (`modules/blue/code_engineer.py`, wired in `orchestrator/wiring.py`) runs on Opus 4.8 rather than the §1-default Sonnet 4.6. This is the narrow runtime counterpart to the build-time "Opus everywhere" preference in `CLAUDE.md`; all other inner-loop calls (the red agent) stay on Sonnet per §1.
- **Dashboard front end:** React 18 plus Vite plus Tailwind, Recharts for plots, React Router 6. Palette is owned by the Claude Design export at `_design_bundle/` and is documented in `_design_bundle/_palette_notes.md` with audience-by-audience rationale. The architecture website at `website/index.html` re-syncs to whatever palette the latest export carries; the constitution does not pin specific hex codes.
- **Test runner:** pytest 8 with `pytest-asyncio`. Coverage minimum 80% per module, measured by `coverage.py`.
- **Static analysis:** `ruff` for lint, `mypy --strict` for types, both run pre-merge. No `# type: ignore` without a numbered ticket reference in the comment.

## 2. Architecture rules

The hexagonal (ports and adapters) layout is constitutional. The orchestrator owns interfaces; modules implement them; modules never import each other.

- **Modules import only from `shared/` and `orchestrator/interfaces/`.** No module imports from another module's package. Enforced by a pre-merge check that fails any pull request with `from modules.<x>` inside `modules/<y>/` (x not equal to y).
- **Interfaces live in `orchestrator/interfaces/`.** Defined as `typing.Protocol`, never as abstract base classes. Per the project preference for protocol-oriented programming.
- **The orchestrator wires modules via dependency injection at startup.** `orchestrator/wiring.py` is the only file allowed to import both a concrete module class and the interface it satisfies.
- **Targets (the systems under evaluation) are not harness code.** The harness ships the Target Protocol and generic adapters (`modules/targets/`); concrete targets/victims live in `examples/targets/` (or external repos) and are wired only at the composition root (`orchestrator/wiring.py`). No harness module imports from `examples/` — enforced by the pre-merge import check.
- **`shared/` contains only data types, cross-cutting infrastructure (persistence client, telemetry, sandbox launcher), and utilities used by two or more pillars.** Anything pillar-specific lives inside the owning module. Enforced by a pre-merge check.
- **Shared-folder changes ride their own branch, never inside a module slice's squash.** Detail in `CONTRIBUTING.md`.
- **The orchestrator's `loop.py` contains no business logic.** It calls interfaces in sequence and writes audit rows. If you find yourself adding a conditional inside `loop.py`, the conditional belongs in a module.

## 3. The core bet

Section 7 of the README and section 8 of the README ("White-box self-test, how the catch rate becomes real") state Crucible's central wager: **independent oracle generation that survives a white-box adversary.** If the oracles only catch attacks against an attacker that does not know the verification scheme, the catch rate is borrowed from the attacker's ignorance, not from the platform's design.

Therefore, constitutional:

- **The white-box self-test runs every pass.** Section 8 of the README is mandatory product behavior, not a stretch goal.
- **The producer sandbox has no path to the verification artifacts.** Held-out test instances, the differential second implementation's outputs, and oracle internals are never readable from inside the producer container. Verified by an integration test that runs a sandboxed job (the local Docker adapter today) and asserts the producer cannot reach the verification artifacts (no network egress, no credentials).
- **Held-out tests are generated after submission, never before.** A static held-out set leaks over time. The held-out oracle generates fresh tests post-submit from the sealed spec.
- **The same red agent does the black-box and the white-box pass.** The catch-rate gap between the two is the report card. No second adversary.

## 4. The transparency-first rule (project CLAUDE.md inheritance)

Every subcomponent's inner workings, where not a security risk, surface in the dashboard. This is the project-level checklist rule in `CLAUDE.md` ("Granular transparency of inner workings"), applied as a constitutional product requirement, not as a stretch goal.

Concretely:

- **Every LLM call carries a trace card** showing prompt, raw response, parsed output, token count, dollar cost. Stored in Postgres `llm_calls` table, surfaced in the dashboard's verdict detail and run views.
- **Every oracle vote exposes its reasoning.** "Which spec obligation did I check, what did I observe, why pass or fail." Stored inline in the audit trace JSON on `verdicts.audit_trace`.
- **Every sandbox execution streams stdout and stderr to the dashboard.** sandbox job logs (stdout/stderr) surface live; no swallowed output.
- **Every subcomponent has a `/health` view** that lists its dependencies, last self-test timestamp, and pass-fail status. The dashboard `/health` route aggregates them.
- **Every action is replayable.** A verdict, a red attack, a blue patch, an oracle vote: each has a "Replay" button in the dashboard. Replay requires deterministic seed capture; the seed is constitutional state on every persisted row.
- **Cost attribution lives on every row.** Each Postgres row that represents work-done has a `pillar` column and a `dollars_spent` column.

Hide only what is a real security risk: Anthropic Application Programming Interface (API) keys, Postgres credentials, sandbox/provider credentials (e.g. a Modal token if the Modal adapter is used).

## 5. Data, never fake

Inherited from the project-level CLAUDE.md hard rule ("NO MOCK / STUB / FAKE / REUSED DATA"):

- Targets train on real datasets. The fraud target uses the Kaggle credit-card fraud detection dataset, downloaded at build time and checksummed.
- Oracles run real checks on real outputs. No placeholder scores, no canned verdicts.
- The strategy catalog populates from real red-agent runs, never from a curated seed list.
- The seeded-hack corpus and leaderboard export contain only attacks that actually succeeded against the running target.
- The Supervisory Letter 11-7 (United States Federal Reserve, SR 11-7) model risk report is generated from the run's actual numbers, never from a template with sample values.

If a number cannot be measured for real (the service is down, the dataset failed to download, the model failed to train), the dashboard renders a typed error explaining the failure, not a sample value.

## 6. Non-negotiables on quality

- **`vouch` runs on every code change.** The fresh-context QA sub-agent (`~/.claude/agents/vouch.md`) is invoked after every slice's code lands and before the slice is reported done. Defined in `QA_ADVERSARY.md`.
- **The submit-gate runs at the end of every assignment-touching response** (`~/.claude/skills/submit-gate/SKILL.md`).
- **Dual-push to GitHub and GitLab on every commit.** `origin` carries two push URLs (GitHub and `labs.gauntletai.com/scottlydon/crucible`); one `git push origin <branch>` fans out to both. Verify with `git ls-remote https://github.com/scott-lydon/crucible.git main` and `git ls-remote gitlab main` returning the same hash.
- **Conventional Commits format.** `<type>(<scope>): <subject>`. Types from the standard list (`feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `build`, `style`, `perf`, `revert`). Scope is the pillar or `shared` or `orchestrator` or `dashboard`.
- **Separate commits per logical unit.** Never squash unrelated changes into one commit.
- **`Assisted-by: Claude` trailer** on commits Claude wrote, per the project CLAUDE.md.

## 7. Things this project does not do

- Crucible does not solve scalable oversight. It instruments the problem and reports residuals.
- Crucible does not target Confidentiality or Availability. Section "What Crucible is not" of the README is binding.
- Crucible does not ship a research-agent target adapter in the two-week build. The adapter shape exists; the implementation is stubbed and skipped at runtime by the orchestrator's `wiring.py`.
- Crucible does not certify any model. It reports a catch rate against a white-box adversary and halts at a residual red line. The certification authority is whoever consumes the model risk report.

## 8. Things Claude (and any agent) must never do

- Catch and swallow exceptions inside business logic. If the producer sandbox fails to launch, the run fails loud with a typed error pointing at the sandbox configuration and the network-egress rule.
- Mock the database in integration tests. Inherited from OpenEMR's CLAUDE.md hard rule.
- Suppress a `mypy --strict` warning. Fix the underlying type.
- Ship code that has not been built, deployed, restarted, and behaviorally verified, per the global CLAUDE.md "DEPLOY-VERIFY-OR-DIE" rule.
- Edit `orchestrator/interfaces/` inside a module slice's branch. Interface changes ride their own branch through the orchestrator owner.
- Edit `shared/` and `modules/<x>/` in the same pull request. Pre-merge check rejects it.

## 9. Cite the rubric line for any decision that touches a rubric pillar

The Gauntlet capstone is graded on Architecture, Scalability, Security, and Testing pillars. Every decision in `plan.md` that touches one of those names the rubric line it advances. This is how `AI_INTERVIEW_PREP.md` later cites back evidence; the evidence chain has to exist by the time the rubric is read against the code.
