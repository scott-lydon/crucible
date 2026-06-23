# Generic Target ADAPTERS (the target-agnostic seam)

This package is the home for generic, victim-agnostic adapters that plug a real
target into the harness through the Target Protocol (`orchestrator.interfaces`).

Future adapters (built in a later slice): `local_model`, `model_endpoint`.

Victims themselves do NOT live here. They live in `examples/targets/` (demo
victims) or are external (customer-provided). The harness reaches them only via
these adapters and the Protocol — never by importing a concrete victim.
