# Contributing to Crucible

Thanks for helping harden AI agents. Crucible is a defensive tool — please keep it that way.

## Setup

```bash
uv venv && . .venv/bin/activate
uv pip install -e ".[dev]"      # add [browser] for the Playwright adapter
pytest -q                       # offline; browser + live-LLM tests auto-skip
ruff check src/ tests/
```

## Golden rules (do not violate)

1. **Operator-owned targets only.** Never add a feature whose headline use is attacking systems
   the user doesn't own. The attestation gate (`--i-own-this-target`) stays.
2. **Fixes are diffs / wrappers, never applied to a live target.**
3. **The held-out firewall is sacred** — the fix engine must never see the held-out attack set.
4. **No over-refusal** — a fix is accepted only if it preserves benign behavior.
5. **Proof over opinion** — prefer deterministic oracles (canaries, tool-interception) over the
   LLM judge; calibrate the judge (`crucible calibrate-judge`) and treat its findings as lower
   confidence.

## Conventions

- Python 3.10+, stdlib-only core (heavy deps go behind optional extras + lazy imports).
- Type hints; structured (typed) findings — no free-text-only results.
- Every new attack class needs: library payloads, an oracle, a fix layer, a ground-truth entry in
  `crucible/verify.py`, and a test.
- Vendored attack corpora must be license-recorded in `THIRD_PARTY.md`.

## Live LLM tests

Off by default (they cost money). Enable with:

```bash
CRUCIBLE_LIVE_LLM_TESTS=1 OPENROUTER_API_KEY=... pytest tests/test_live_openrouter.py
```

## Tests must pass and ruff must be clean before a PR.
