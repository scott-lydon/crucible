# Held-out oracle

The first of the four non-colluding oracles. Implements
`orchestrator.interfaces.Oracle`.

## Interface contract

- `verify(spec, attack_input, output) -> OracleVote`: Opus generates assert
  statements from the spec's obligations *after* submission, the producer
  output and those asserts run together in the sealed sandbox, and the oracle
  votes `pass` (all asserts held), `fail` (an assert raised), or `unavailable`
  (the output was not source code, or the model produced no tests). The reason
  string carries the failing line for `fail`.
- `weight`: 1.0 (a full oracle vote; the LLM judge alone carries 0.5).
- `self_test() -> ProbeResult`: green when a docker daemon is present (the
  tests run in the sandbox), amber otherwise.

## Why it catches what a fixed suite cannot

The tests are generated fresh from the sealed spec after the producer submits,
so the producer cannot have trained against them, and they are deleted after
the run so they cannot leak to a later run. The producer never sees them: it
runs sealed, and the spec is read server-side through `SpecResolver`, a path
the no-network sandbox cannot reach.

## Testing

Unit tests inject `ScriptedLlmClient` (canned asserts) and the real
`DockerSandbox`, so the generate-compose-run-vote path is exercised in CI
without an LLM call. The live test (opt-in) uses real Opus.
