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
