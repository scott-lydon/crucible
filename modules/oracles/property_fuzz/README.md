# Property-fuzz oracle

The fourth of the four non-colluding oracles. Implements
`orchestrator.interfaces.Oracle`.

## Interface contract

- `verify(spec, attack_input, output) -> OracleVote`: Sonnet writes a `fuzz()`
  function that samples many random inputs and asserts spec-guaranteed
  properties. It runs against the producer output in the sealed sandbox via the
  shared check runner. Votes `fail` when a property is violated on some sampled
  input (with the offending input), `pass` when no violation is found,
  `unavailable` when the output is not source or the harness itself errors.
- `weight`: 1.0.
- `self_test() -> ProbeResult`: green when a docker daemon is present.

## Why stdlib random, not the Hypothesis library

The sealed sandbox runs `--network none`, so it cannot install hypothesis, and
bundling a hypothesis image is deferred. Random sampling with the standard
library finds violations all the same, which is the done-criterion. The
shrinking and strategy sophistication of Hypothesis is the known trade-off.

## Testing

Unit tests inject `ScriptedLlmClient` (a canned `fuzz()` function) and the real
`DockerSandbox`: a correct implementation passes, a broken one is caught. The
live path uses real Sonnet.
