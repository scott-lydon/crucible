# Metamorphic oracle

Re-asks the producer the same question under neutral, meaning-preserving transforms (for
the fraud model, scaling or reordering that must not change the label; for an agent,
paraphrases of the same request). A correct producer gives a stable answer. The oracle
fires when a neutral transform flips the decision, which means the producer is steerable
by phrasing or representation alone rather than by the substance of the input. It carries
one full vote (weight 1.0).

## Interface contract

- `vote(spec, attack, output) -> OracleVote`: applies the metamorphic relations and
  fires when one is violated, naming which relation broke.
- `weight`: **1.0** (one of the four independent mechanical oracles).
- `health() -> HealthStatus`: green when the producer can be re-queried.

It re-queries the RUN's actual target (bound by the loop), so it grades the agent under
test, not a default.
