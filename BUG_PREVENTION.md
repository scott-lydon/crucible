# Bug / issue prevention checklist

Brief-enough-to-work notes on bugs fixed in Crucible and how to avoid the class
next time. Reviewed when adding a new oracle, target, or LLM-driven check.

## 1. LLM-generated checks must use concrete literals, not free variables

**Bug (slice 6, metamorphic oracle):** Sonnet wrote metamorphic relations with
symbolic variables, for example `assert add(a, b) == add(b, a)`, where `a` and
`b` were never defined in the composed script. Running them raised `NameError`,
which failed for BOTH a correct and a wrong implementation.

**Prevention:**
- Any prompt that asks an LLM for runnable assert checks must require concrete
  literal inputs and forbid undefined variables. See `MetamorphicOracle.generate_rules`.
- Never blame the producer for the check harness's own error. Distinguish an
  `AssertionError` (producer violated the check, vote FAIL) from any other
  exception (the generated check is malformed, vote UNAVAILABLE). Centralized in
  `shared/sandbox/check_runner.py` (`run_python_checks`), used by every
  assert-running oracle so the rule lives in one place.

## 2. Frozen value objects vs Protocol instance-variable members

**Bug (slices 3, 5):** a frozen dataclass field does not satisfy a Protocol
member declared as a plain (settable) instance variable, so `mypy` rejected
`CodeAgentTarget`/oracles as not implementing the interface.

**Prevention:** declare immutable Protocol attributes as read-only `@property`
(see `Target.target_type`, `Oracle.name`, `Oracle.weight`). Then both a plain
class attribute and a frozen dataclass field satisfy them.

## 3. Async engine connections must not cross event loops in tests

**Bug (slice 0):** a pooled asyncpg connection reused on a later pytest-asyncio
loop raised "Event loop is closed" at teardown.

**Prevention:** the test engine uses `NullPool` (`reset_engine_for_tests`), so
no connection is pooled across per-test loops.

## 4. Alembic autogenerate requires the database at head first

**Bug (slices 5, 6):** `alembic revision --autogenerate` errored with "Target
database is not up to date" when the dev database had not been upgraded.

**Prevention:** run `alembic upgrade head` before autogenerating a new revision.

## 5. The red agent's task is refused by the model without a research frame

**Bug (slice 11, red search):** pointed at the real fraud model, real Sonnet
intermittently refused "propose a transaction that evades the fraud detector,"
returning a safety redirect ("discussing evasion at a conceptual level... what's
the actual context here?") instead of a JSON proposal. The parser then recorded
every refused turn as a `malformed-proposal`, so the live search found zero
evasions even though the scripted path passed. The scripted test could never
catch this: a canned LLM never refuses.

**Prevention:**
- Any LLM driven to do adversarial / red-team work must carry a system prompt
  that states the legitimate, authorized, defensive context (`_RESEARCH_SYSTEM`
  in `modules/red/search.py`, passed via `LlmClient.call(system=...)`). The
  framing must be accurate, not a jailbreak: Crucible really is a sealed-lab
  defensive platform.
- Always run at least one opt-in LIVE test against the real model for any new
  LLM-driven path; a scripted double cannot surface a real refusal.

## 6. Evasion threshold must match the target's decision threshold

**Note (slice 11):** the fraud model scores almost every arbitrary input near
0.0 (fraud is a rare class), so a fixed `evasion_threshold` of 0.5 makes any
valid proposal "evade." That is fine for proving the search-and-catalog
mechanics, but the meaningful evasion bar is the target's actual operating
decision threshold.

**Prevention:** calibrate `RedSearchAgent.evasion_threshold` to the target's
real decision threshold (and define it against the held-out attack set) when the
blue loop and white-box recall land, rather than trusting the 0.5 default.

## 7. Fake values from Claude Design surviving into the live dashboard

**Issue.** The Claude Design export ships happy-state mocks with literal sample values (a 92.3% attack-success-rate, a $142.50 cost meter, an ISO date on a run row). The verbatim-copy rule means those values land in `dashboard/src/pages/` unchanged. Once the dashboard is running, a stubbed tile is visually indistinguishable from a real measurement, which is the exact failure mode `coding-practices.md` section 4 ("Data, never fake") forbids.

**Prevention.**
- Every fabricated value in a Claude Design happy-state mock is wrapped in the canonical label `__CLAUDE_DESIGN_STUB__[<key>|<kind>|<hint>]__<visibleValue>__/CLAUDE_DESIGN_STUB__` per `design/claude-design-brief.md` and `docs/CLAUDE_DESIGN_STUB_PROTOCOL.md`.
- After every re-export, run `uv run python scripts/strip_claude_design_stubs.py --bundle-dir _design_bundle/` to replace the labels with `CLAUDE_DESIGN_WIRE_ME_UP[<key>|<kind>]` placeholders and emit `_design_bundle/_claude_design_stub_manifest.json` as the wire-up work list.
- The pre-merge gate runs `uv run python scripts/audit_claude_design_stubs.py`. Exit code 2 (unstripped `__CLAUDE_DESIGN_STUB__` in a code path) and exit code 3 (heuristic indicators of unmarked fake data in `dashboard/src/`) block the merge. Exit code 1 (`CLAUDE_DESIGN_WIRE_ME_UP` placeholders remaining) blocks the final ship but is allowed mid-build.
- Apply the same checklist to any new product or feature that touches an operator-facing surface: every literal value must come from a hook reading real data, or render the typed "Not yet measured" sentinel from section 4.
