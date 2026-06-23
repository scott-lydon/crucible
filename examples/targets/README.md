# Demo victims

The systems Crucible evaluates. **NOT part of the harness.**

Real targets are external (customer-provided) and reached via adapters in
`modules/targets/` through the Target Protocol. The demo victims here exist only
to exercise and showcase the harness end-to-end.

These may be extracted to a separate repo with zero harness changes because they
import only the Protocol (`orchestrator.interfaces`) + shared types (`shared.*`).

- `fraud_synth/` — a synthetic transaction generator, a sealed ground-truth
  fraud rule (`is_fraud`), and a deliberately `FlawedDetector` that over-relies
  on transaction amount. The harness's red/oracle pillars expose that flaw.
