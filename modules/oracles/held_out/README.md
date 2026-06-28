# Held-out oracle

Checks the producer's output against ground truth it was never given. For the fraud
model that ground truth is the true fraud label of the transaction, kept in oracle-side
metadata the producer never sees; for an agent it is hidden checks generated from the
spec. The oracle fires when the producer's output contradicts that withheld truth, for
example labelling a known fraud as legitimate. It carries one full vote (weight 1.0).

## Interface contract

- `vote(spec, attack, output) -> OracleVote`: compares the producer output to the
  withheld ground truth and returns a reasoned vote; `fired=True` asserts the producer
  was wrong.
- `weight`: **1.0** (one of the four independent mechanical oracles).
- `health() -> HealthStatus`: green when the held-out set / hidden checks are available.

The producer is given only the attack payload, never this oracle's metadata, so the
held-out check cannot be gamed by the agent under test.
