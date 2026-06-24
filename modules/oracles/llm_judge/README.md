# LLM judge oracle

The fifth member of the verification ensemble, and deliberately the weakest.
Implements `orchestrator.interfaces.Oracle`.

## Interface contract

- `verify(spec, attack_input, output) -> OracleVote`: one large language model
  (Opus) reads the produced artifact, judges it against the sealed spec's
  obligations, and returns a JSON verdict that is parsed into a vote. Votes
  `pass` or `fail` with the model's one-paragraph reason, or `unavailable` when
  the artifact is empty or the model's response is not a parseable pass / fail
  verdict (it is never guessed into a pass or a fail).
- `weight`: **0.5**. The judge carries half a vote, so it can never on its own
  push a verdict past the aggregator's 2.0 pass threshold (US-4,
  `ARCHITECTURE.md` section 3). The verdict view marks its card "one vote".
- `self_test() -> ProbeResult`: green when the `claude` CLI is on PATH or a
  scripted client is wired (mock-LLM), amber otherwise. The judge runs nothing
  in the sandbox, so it needs no docker daemon, only the model.

## Why a single LLM is included at all

The proposal includes a large language model judge "as one measured approach
among several, never the sole authority" (proposal section 3, Pillar 1). A lone
judge shares the producer's blind spots, which is exactly why it does not get a
full vote. Keeping it in the ensemble at half weight lets the dashboard measure
how often the judge agrees with the four mechanical oracles it cannot overrule,
which is itself a reported number rather than a trusted one.

## Target-agnostic artifact rendering

A code submission is read as-is; any structured output (a fraud score, for
example) is JSON-serialized before the judge reads it, so the oracle is not
code-only. Oversized artifacts are truncated to keep the prompt and its cost
bounded; a realistic submission is well under the cap.

## Testing

Unit tests inject `ScriptedLlmClient` with canned judge responses and assert
the vote logic (pass, fail, unavailable, and malformed-response handling)
without any network or docker. The live path uses real Opus and is opt-in via
`CRUCIBLE_RUN_LLM_TESTS=1` in `tests/integration/test_llm_judge_oracle.py`.
