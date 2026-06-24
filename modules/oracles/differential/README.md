# Differential oracle

The third of the four non-colluding oracles. Implements
`orchestrator.interfaces.Oracle`.

## Interface contract (code mode)

- `verify(spec, attack_input, output) -> OracleVote`: generates a second
  implementation from a different model family (Haiku, versus the producer's
  Sonnet), generates concrete comparison inputs, runs both implementations on
  those inputs in the sealed sandbox, and compares. Votes `fail` when the two
  families disagree on any input (neither is trusted as ground truth; the
  disagreement itself is the signal), `pass` when they agree on all,
  `unavailable` when the output is not source, the second implementation does
  not parse, or too few inputs are synthesized.
- `weight`: 1.0.
- `self_test() -> ProbeResult`: green when a docker daemon is present.

## Why it catches what one model cannot

A second implementation from a different family fails differently. Where the
two disagree, at least one is wrong, so the platform refuses to certify without
declaring which side is right. Same family, different seed would share blind
spots and defeat the cross-check.

## Fraud variant

`ARCHITECTURE.md` also specifies a fraud differential (LightGBM versus an
IsolationForest from a different family). That variant is a follow-on; this
slice ships the code differential, the canonical cross-family mechanism.

## Testing

Pure tests cover the harness builder and report parser without docker. Sandbox
tests inject `ScriptedLlmClient` (a canned second implementation and inputs)
and run the real comparison; the live path uses real Haiku and Sonnet.
