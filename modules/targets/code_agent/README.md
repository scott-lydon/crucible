# Code-agent target

A Shape 2 `Target`: produces Python source for a sealed spec via the LLM
(Sonnet by default), through the local Claude Max CLI.

## Interface contract

Implements `orchestrator.interfaces.Target`:

- `submit(spec, attack_input) -> TargetOutput`: prompts the model to implement
  the spec as a single Python module, extracts the source (fenced or bare),
  and returns it. `score` is 1.0 when the source parses (`ast.parse`), else
  0.0. The audit records the model, the per-call cost, and the validity flag.
- `query_target(attack_input) -> float`: a probe that returns the syntactic
  validity (1.0 or 0.0) of producing code for the given input. It synthesizes a
  minimal spec from the input, since `query_target` carries no spec.
- `self_test() -> ProbeResult`: a fast readiness probe. It reports the wired
  client and model and, for the real CLI client, whether `claude` is on PATH.
  It does not run a full generation on every poll (seconds and real quota).

## Sandbox

Slice 3 only produces source. Running the produced code inside the sealed
sandbox (Docker first, Modal as the hosted target) lands in slice 4.

## Testing

Unit tests drive the target with `ScriptedLlmClient` (no real call). The
done-criterion live test (`tests/integration/test_code_agent_target.py`)
calls the real CLI and asserts the output passes `ast.parse`; it runs only
when `CRUCIBLE_RUN_LLM_TESTS=1` and `claude` is on PATH.
