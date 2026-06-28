# Differential oracle

Answers the same input with a DIFFERENT mechanism and fires when the two diverge. For
the fraud model that second mechanism is a different model family (an IsolationForest
anomaly detector) whose fraud-like verdict contradicts the producer's "legitimate"; for
an agent it is a different reference LLM asked how a policy-abiding agent should respond,
which fires when the producer complied where the safe reference declined. Because the two
do not share blind spots, a hack that slips past the producer is caught here. It carries
one full vote (weight 1.0).

## Interface contract

- `vote(spec, attack, output) -> OracleVote`: runs the reference mechanism on the same
  input and fires on divergence from the producer's output.
- `weight`: **1.0** (one of the four independent mechanical oracles).
- `health() -> HealthStatus`: green when the reference model / detector is loaded.

The reference is deliberately a different family from the producer, so the two are
unlikely to be wrong in the same way.
