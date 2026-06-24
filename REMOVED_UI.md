# Removed UI (out of PRD scope)

Per the 2026-06-24 decision: the Claude Design pages shipped with sections that
go beyond the capstone proposal (`Crucible_Capstone_Proposal`). Rather than
fabricate backends for them or leave stub data on screen, those out-of-scope
sections are removed from the live `.dc.html` pages and logged here so they can
be re-added later if a backend and a real need materialize.

The rule applied to every Tier C page: keep the design markup verbatim EXCEPT
mocked/stubbed data, which is wired to a real backend route or rendered as
em-dash; any section with no PRD basis and no backing route is removed and
listed below.

## Removed sections

| Page | Section removed | Why out of PRD | Re-add when |
|------|-----------------|----------------|-------------|
| slice-08 halt | Blocked-runs queue | No run-queue backend; the PRD halt only stops new certification (US-13), it does not model a per-run block queue | a runs-queue/blocked-state route exists |
| slice-08 halt | Halt history table | No halt-history backend; `/halt` returns only the single current state | a halt-history route/table exists |
| slice-08 halt | Lift-conditions + override workflow | No lift/override backend or governance route; beyond the PRD's "stop certifying below the red line" | a lift-conditions/override route exists |
| slice-08 halt | Per-round debounce trace | No per-round recall-window backend; `HaltRule` compares the latest recall to the threshold, no debounce | a per-round recall-window route exists |
