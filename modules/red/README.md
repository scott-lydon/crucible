# Red pillar

Pillar 2: the LLM-driven adversarial search engine and its strategy catalog.
Implements `orchestrator.interfaces.RedAgent`.

## Interface contract

- `RedSearchAgent.search(spec, target, budget, run_id, *, white_box) -> list[Attack]`:
  reason about why prior attempts were caught, propose a new distinct tactic,
  query the target through `query_target()`, and iterate until the budget
  (attempts or dollars) is spent. Returns every attempt, each marked succeeded
  or not, so attack-success-rate is computed over the whole search. The agent
  persists nothing; the caller persists the attacks and records the successful
  ones in the catalog.
- Success here is an evasion measured by the target's own signal: a detector
  scoring the adversarial input below `evasion_threshold` (0.5 by default) is an
  evasion. The reward-hack sense (an artifact slipping past the oracle ensemble)
  is computed by the loop once it drives the oracles over the red output; that
  is the wiring in the slice that follows.
- White-box mode is threaded and marks each attempt `white_box=true`; the full
  verification-scheme injection into the prompt lands in the white-box slice
  (US-14).

## Strategy catalog (US-6)

`StrategyCatalog` records every successful evasion twice: a Postgres row (one
per tactic per target type, with a reuse count and running dollar total, so the
average dollars-to-succeed is the real mean) and an append-only JSONL discovery
log on disk. `/catalog` reads the table, most-reused first. The catalog carries
no foreign key to runs on purpose, so it outlives any single run as a reusable
benchmark.

## Testing

`tests/test_search.py` drives the search with a sequenced in-test LLM double and
a fixture detector, with no network: distinct tactics are found, the budget
caps the search, and a malformed proposal becomes a clean failed attempt rather
than a crash. `tests/integration/test_catalog.py` runs the search, records the
successes, and asserts at least three distinct tactics surface at `/catalog` on
real Postgres. The live path (real Sonnet versus the real fraud target) is
opt-in via `CRUCIBLE_RUN_LLM_TESTS=1`.
