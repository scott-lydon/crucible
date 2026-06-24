# Dummy target

A canned `Target` for the slice-1 loop smoke test.

## Interface contract

Implements `orchestrator.interfaces.Target`:

- `submit(spec, attack_input) -> TargetOutput`: returns a deterministic echo of
  the input under the spec's first obligation, with a reproducible score.
- `query_target(attack_input) -> float`: a deterministic pseudo-score in
  `[0, 1]` derived from the input length. No randomness, so replays match.
- `self_test() -> ProbeResult`: green when the target returns a score.

## Why it exists

It lets the orchestrator drive a target end to end (wiring, submit,
persistence) before a real model target (fraud, slice 2) or LLM target
(code agent, slice 3) exists. It is the `DUMMY` target type and
`orchestrator/wiring.py` never selects it for a production run.
