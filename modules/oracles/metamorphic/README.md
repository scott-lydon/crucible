# Metamorphic oracle

The second of the four non-colluding oracles. Implements
`orchestrator.interfaces.Oracle`.

## Interface contract

- `generate_rules(spec) -> list[str]`: Sonnet synthesizes at least three
  metamorphic relations (commutativity, identity, increment laws, and similar)
  as assert statements, derived from the spec's invariants and obligations.
- `verify(spec, attack_input, output) -> OracleVote`: composes the producer
  output with the relations and runs them in the sealed sandbox. Votes `pass`
  (all relations held), `fail` (a relation broke), or `unavailable` (output not
  source code, or fewer than `min_rules` relations synthesized).
- `weight`: 1.0.
- `self_test() -> ProbeResult`: green when a docker daemon is present.

## Why it catches what a fixed suite cannot

A metamorphic relation needs no reference answer, so it probes correctness from
an angle a held-out test set may miss: it asserts how the output must *change*
when the input changes, catching a producer that is wrong in a structured way.

## Testing

Unit tests inject `ScriptedLlmClient` (canned relations) and the real
`DockerSandbox`. The live test (opt-in) uses real Sonnet and asserts at least
three relations are synthesized.
