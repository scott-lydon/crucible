# Coding practices

How Crucible is built. Every rule here is current and binding. A violation blocks merge;
it is not "tech debt."

Scope: this file says **how** to build, never **what** to build. Functionality lives in
`ARCHITECTURE.md` (topology, the core bet, out of scope) and `acceptance-tests.md` (user
stories, behavior). Keep functionality clauses out of this file. A "you may not build X"
rule hidden among style rules silently vetoes real features, so it does not belong here.

Term definitions for every recurring noun live in
[`docs/VOCABULARY.md`](docs/VOCABULARY.md). When a sentence uses "model," "retrain,"
"catch," "target," or "producer," that file is the canonical referent.

## 1. Stack

- **Language:** Python 3.12. Forced by the machine-learning targets (LightGBM,
  scikit-learn, autoencoders), the Anthropic Software Development Kit (SDK), and
  `hypothesis` for property-based fuzzing.
- **Web framework:** FastAPI. Single `POST /runs` endpoint streaming Server-Sent
  Events (SSE).
- **Persistence:** Postgres 16 (Supabase free tier in development, Render Postgres in
  production). SQLite is forbidden in code paths shared with the orchestrator;
  concurrent writes from two pillars will break it.
- **Object-relational mapping (ORM):** SQLAlchemy 2.x in async mode, with Alembic for
  migrations. No raw SQL outside `shared/persistence/`.
- **Producer sandbox:** Modal. The producer container has no environment variables and
  no network access to Postgres or the verification artifact bucket.
- **Large language model (LLM) provider:** Anthropic Claude. Sonnet 4.6 on the inner
  red and blue loops; Opus 4.8 on the judge oracle and the white-box self-test pass.
  No other provider; no fallback to OpenAI or Google for "redundancy." Cross-family in
  the differential oracle is satisfied by the two model families (LightGBM versus
  IsolationForest for fraud; Sonnet versus Haiku for code), not by mixing vendors.
- **LLM access path:** calls go through the local `claude` command-line interface
  (CLI), authenticated with the operator's Claude Max subscription, with the model
  chosen per call via `--model`. Local development and the live demo need no metered
  Anthropic key; the CLI still reports `total_cost_usd` per call, which feeds the
  `dollars_spent` transparency column. A metered `ANTHROPIC_API_KEY` is a deploy-time
  fallback only, for a server that has no Claude CLI session.
- **Dashboard front end:** React 18 plus Vite plus Tailwind, Recharts for plots, React
  Router 6. Palette is owned by the Claude Design export at `_design_bundle/` and is
  documented in `_design_bundle/_palette_notes.md` with audience-by-audience rationale.
  The architecture website at `website/index.html` re-syncs to whatever palette the
  latest export carries; this file does not pin specific hex codes.
- **Test runner:** pytest 8 with `pytest-asyncio`. Coverage minimum 80% per module,
  measured by `coverage.py`.
- **Static analysis:** `ruff` for lint, `mypy --strict` for types, both run pre-merge.
  No `# type: ignore` without a numbered ticket reference in the comment.

## 2. Module and interface discipline (the hexagonal rule)

The hexagonal (ports and adapters) layout is a build practice, enforced pre-merge. The
orchestrator owns interfaces; modules implement them; modules never import each other.
The structural picture of this layout lives in `ARCHITECTURE.md` sections 1 and 2; the
rules that keep it honest live here.

- **Modules import only from `shared/` and `orchestrator/interfaces/`.** No module
  imports from another module's package. Enforced by a pre-merge check that fails any
  pull request with `from modules.<x>` inside `modules/<y>/` (x not equal to y).
- **Interfaces live in `orchestrator/interfaces/`.** Defined as `typing.Protocol`,
  never as abstract base classes. Per the project preference for protocol-oriented
  programming (see section 6).
- **The orchestrator wires modules via dependency injection at startup.**
  `orchestrator/wiring.py` is the only file allowed to import both a concrete module
  class and the interface it satisfies.
- **`shared/` contains only data types, cross-cutting infrastructure (persistence
  client, telemetry, sandbox launcher), and utilities used by two or more pillars.**
  Anything pillar-specific lives inside the owning module. Enforced by a pre-merge
  check.
- **Shared-folder changes ride their own branch, never inside a module slice's
  squash.** Detail in `CONTRIBUTING.md`.
- **Interface changes ride their own branch through the orchestrator owner.** A pillar
  owner never edits `orchestrator/interfaces/` inside a module slice's branch.
- **The orchestrator's `loop.py` contains no business logic.** It calls interfaces in
  sequence and writes audit rows. If you find yourself adding a conditional inside
  `loop.py`, the conditional belongs in a module.

## 3. Transparency-first

Every subcomponent's inner workings, where not a security risk, surface in the
dashboard, on every persisted row.

- **Every LLM call carries a trace card** showing prompt, raw response, parsed output,
  token count, dollar cost. Stored in Postgres `llm_calls` table, surfaced in the
  dashboard's verdict detail and run views.
- **Every oracle vote exposes its reasoning.** "Which spec obligation did I check, what
  did I observe, why pass or fail." Stored inline in the audit trace JSON on
  `verdicts.audit_trace`. An audit trace that records only "ok" or "failed" is a bug.
- **Every sandbox execution streams stdout and stderr to the dashboard.** Modal job
  logs surface live; no swallowed output.
- **Every subcomponent has a `/health` view** that lists its dependencies, last
  self-test timestamp, and pass-fail status. The dashboard `/health` route aggregates
  them.
- **Every action is replayable.** A verdict, a red attack, a blue patch, an oracle
  vote: each has a "Replay" button in the dashboard. Replay requires deterministic seed
  capture; the seed is state on every persisted row.
- **Cost attribution lives on every row.** Each Postgres row that represents work-done
  has a `pillar` column and a `dollars_spent` column.

Hide only what is a real security risk: Anthropic Application Programming Interface
(API) keys, Postgres credentials, Modal tokens.

## 4. Data, never fake

Never use mock, stub, placeholder, or reused data, and never present simulated or cached
output as a real, fresh result.

- Targets train on real datasets. The fraud target uses the Kaggle credit-card fraud
  detection dataset, downloaded at build time and checksummed.
- Oracles run real checks on real outputs. No placeholder scores, no canned verdicts.
- The strategy catalog populates from real red-agent runs, never from a curated seed
  list.
- The seeded-hack corpus and leaderboard export contain only attacks that actually
  succeeded against the running target.
- The Supervisory Letter 11-7 (United States Federal Reserve, SR 11-7) model risk
  report is generated from the run's actual numbers, never from a template with sample
  values.

If a number cannot be measured for real (the service is down, the dataset failed to
download, the target failed to train or patch, for example `LGBMClassifier.fit(...)`
crashed for the Shape 1 fraud LightGBM classifier, or the agent-configuration diff
failed to apply for the Shape 2 code agent), the dashboard renders a typed error
explaining the failure, not a sample value.

## 5. Commit and review conventions

- **Dual-push to GitHub and GitLab on every commit.** `origin` carries two push URLs
  (GitHub and `labs.gauntletai.com/scottlydon/crucible`); one `git push origin
  <branch>` fans out to both. Verify with `git ls-remote
  https://github.com/scott-lydon/crucible.git main` and `git ls-remote gitlab main`
  returning the same hash.
- **Conventional Commits format.** `<type>(<scope>): <subject>`. Types from the
  standard list (`feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `build`,
  `style`, `perf`, `revert`). Scope is the pillar or `shared` or `orchestrator` or
  `dashboard`.
- **Separate commits per logical unit.** Never squash unrelated changes into one
  commit.
- **`Assisted-by: Claude` trailer** on commits an AI assistant helped write.

## 6. Language and style conventions

The language style guide is the Python equivalent of the Google Swift Style Guide:
[PEP 8](https://peps.python.org/pep-0008/) plus the
[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html). Where
this section is silent, those two are the tie-breaker.

### Design principles (CUPID, and the four-letter acronyms)

Follow [CUPID](https://cupid.dev): **C**omposable (plays well with others),
**U**nix-philosophy (does one thing well), **P**redictable (does what you expect),
**I**diomatic (feels natural in Python), **D**omain-based (the code models the problem
domain in language and structure). Reinforced by DRY (do not repeat yourself), YAGNI
(you are not going to need it), KISS (keep it simple), SPOT (single point of truth),
and SOI (SOLID without the L and the D: polymorphism is avoided in favor of protocols,
which in Python means `typing.Protocol`, not class inheritance).

### Protocol-oriented over inheritance

Prefer `typing.Protocol` over abstract base classes and over class inheritance for any
cross-boundary contract. Pillar interfaces are Protocols (see section 2). Reach for
inheritance only when a single concrete implementation genuinely shares state with its
subtypes, which in this codebase is rare.

### Type augmentation: put the function where it is findable and reusable

Put a function on the type it naturally belongs on, not in a service class (the Swift
type-augmentation preference, applied in Python). Use a method on the domain type when
the behavior is intrinsic to that type; a module-level function in the module that owns
the domain concept when the behavior spans types; and a `@classmethod` constructor on
the value object for parsing. Do not invent a `FooManager` or `FooHelper` service class
to hold a function that belongs on `Foo`.

### Strict typing

- Every property, parameter, and return type carries a native annotation. `mypy
  --strict` is the floor, not the ceiling.
- Value objects, DTOs, and configuration are `@dataclass(frozen=True, slots=True)`.
  Mutable state is the exception, justified in a comment.
- Wrap primitives that could be confused for one another (a `RunId` versus an
  `AttackId`, a dollar `Money` versus a count) in a typed value object, so an argument
  transposition is a type error, not a runtime surprise.
- Parse, do not validate: at the FastAPI boundary, the command-line interface (CLI),
  and the sandbox-job entry, parse raw input into typed objects immediately, so
  downstream code works with types that guarantee their own validity.
- Narrow, do not cast. When a value is a union or `object`, narrow with `isinstance`,
  never coerce with `str(...)` or `int(...)` to silence the type checker.

### Errors must be loud, typed, and self-explaining

- **Let exceptions propagate.** Catch only where the caller can meaningfully recover.
  Do not catch-log-continue; it hides failures from the orchestrator loop, which is the
  one place that turns a failure into a typed verdict for Measure.
- **Catch sites are allowed only at the FastAPI boundary and at sandbox-job entry.**
  Everywhere else, the exception rides up.
- **Every failure case throws a clear, comprehensive, specific error,** built so that
  diagnosing and even fixing the issue is immediately obvious. The message names what
  operation failed, the concrete inputs in play, and, where knowable, the likely fix.
  When the producer sandbox fails to launch, the run fails loud with a typed error
  pointing at the Modal token and the network egress rule, not a generic "sandbox
  error."
- **Use structured logging context, never string interpolation.** Pass variables as a
  context dict (`logger.error("failed to send", phone=phone, exc_info=e)`), not baked
  into the message string.
- **Never expose an exception's raw message in user-facing output.** It may carry
  Structured Query Language (SQL) or file paths. Log the exception; return a generic
  message to the user.
- **Wherever anything could err, add comprehensive debugging** so the error message is
  enough to (1) identify the issue immediately and (2) suggest an appropriate fix.
  Whenever a fix is applied after back-and-forth, also upgrade the surrounding error
  reporting so that class of issue surfaces itself next time.

### Comments

Every function that could create a "what the heck is this" moment gets a comment, or is
rewritten so the moment cannot arise. Comments explain why, not what; the code already
says what.

### Outward-facing text carries no dash punctuation

Anything a reader other than the maintainer will see (commit messages, pull request
descriptions, user-facing strings, docs, the architecture website, the SR 11-7 report)
contains zero em dashes, en dashes, or spaced hyphens used as a pause. Rewrite with a
comma, a period, a colon, parentheses, or two sentences. Hyphens inside genuine
compound words, code, identifiers, file paths, flags, and numeric ranges are fine.

## 7. Things any agent must never do

- Catch and swallow exceptions inside business logic (see section 6).
- Mock the database in integration tests.
- Suppress a `mypy --strict` warning. Fix the underlying type.
- Ship code that has not been built, deployed, restarted, and behaviorally verified.
- Edit `orchestrator/interfaces/` inside a module slice's branch. Interface changes
  ride their own branch through the orchestrator owner.
- Edit `shared/` and `modules/<x>/` in the same pull request. The pre-merge check
  rejects it.

## 8. Cite the rubric line for any decision that touches a rubric pillar

The project is graded on Architecture, Scalability, Security, and Testing pillars. Every
decision in `ARCHITECTURE.md` that touches one of those names the rubric line it
advances, so the evidence chain exists by the time the rubric is read against the code.
The rubric-pillar mapping table lives in `acceptance-tests.md` section 3.
