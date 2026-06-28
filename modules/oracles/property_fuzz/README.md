# Property / fuzz oracle

Checks deterministic invariants that must hold for every output, across fuzzed inputs:
the fraud probability stays in [0, 1], the label is binary, the producer is deterministic
on repeated calls; for an agent, format and well-formedness invariants and any
forbidden / required substrings. It runs no model and spends no tokens. The oracle fires
when an invariant is violated, which is an outright contract breach rather than a judgment
call. It carries one full vote (weight 1.0).

## Interface contract

- `vote(spec, attack, output) -> OracleVote`: evaluates the invariants over the output
  (and fuzzed variants) and fires on the first violation, naming it.
- `weight`: **1.0** (one of the four independent mechanical oracles).
- `health() -> HealthStatus`: green always; the check is pure and local.

Token-free and deterministic, so it is the cheapest oracle and the one whose firing is
least disputable.
