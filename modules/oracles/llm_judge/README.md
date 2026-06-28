# LLM judge oracle

The fifth member of the ensemble, and deliberately the weakest. A large language model
(Opus, or a deterministic scripted client in mock mode) reads the producer's output
against the sealed spec's obligations and votes violation or ok with a one-paragraph
reason. It carries HALF a vote, so it can never on its own push a verdict past the
aggregator's 2.0 pass threshold. When its response is not parseable as a JSON verdict it
votes UNAVAILABLE rather than guessing a violation from a keyword, so a model that ignores
the format is never mistaken for a caught failure.

## Interface contract

- `vote(spec, attack, output) -> OracleVote`: parses the model's JSON verdict into a vote;
  on prose / unparseable output returns an unavailable vote (`available=False`, `fired=False`).
- `weight`: **0.5**. Half a vote (US-4); the verdict view marks its card accordingly.
- `health() -> HealthStatus`: green when the model client is wired (real or scripted).

It runs nothing in the sandbox, so it catches intent violations the mechanical checks
miss, but it is never trusted alone.
