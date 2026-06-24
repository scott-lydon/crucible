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
| slice-16 specs | Spec diff view (vN → vN+1) | No spec-diff backend; `/specs/history` returns rows, not diffs | a spec-diff route exists |
| slice-16 specs | Reviewer signatures panel | No signature/governance backend; out of PRD scope | a signatures route exists |
| slice-16 specs | Provenance-chain panel | No provenance/hash-chain backend; out of PRD scope | a provenance route exists |
| slice-16 specs | Timeline approved/retired states + patch counts | `/specs/history` has no lifecycle state or patch count per spec | spec-lifecycle fields exist |
| slice-10 whitebox | Per-family seeded-corpus recall table (6 families × 40) | No per-family recall backend; `/metrics` gives a single white-box recall | a per-family recall route exists |
| slice-10 whitebox | Recall headline per-family bars + Wilson CI + "221 of 240" | Same: no per-family/seeded-corpus counts in the backend | a seeded-corpus route exists |
| slice-10 whitebox | Signed disclosure-manifest line (run id, reviewer, date) | No disclosure-manifest backend; out of PRD scope | a manifest route exists |
| slice-14 SR-report | Fabricated KPI grid + static report sections (exec summary, governance, halt, lineage, sign-off) | Replaced by the real `/reports/{runId}` Markdown render; the backend produces the report from real run rows, not a static design | structured per-section report route exists |
| slice-07 blue-patch | Reviewer-actions/approval workflow, fabricated diff + provenance sections | No patch-review/approval backend; `/blue/{id}` returns the patch + held-out validation + model version, not an approval workflow | a patch-approval route exists |
