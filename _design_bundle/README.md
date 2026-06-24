# Crucible Design Bundle

This directory holds the Claude Design export, sliced by route. Per the global `~/.claude/CLAUDE.md` "CLAUDE DESIGN FIDELITY" hard rule, the contents of this folder are copied verbatim into `dashboard/src/pages/` once the slice converges through UX persona review.

## Layout

```
_design_bundle/
  _palette_notes.md                  Claude Design's palette decision, hex codes, audience rationale
  slice-01-run-launcher/
    v1.html                          first generation
    v2.html                          after persona-feedback iteration 1
    ...
    FINAL.html                       converged or capped (capped slices ship CONVERGED_AT_CAP.md alongside)
    feedback/
      iter-01/
        bank-risk-officer.json
        codegen-vendor-eng.json
        public-sector-procurement.json
      iter-02/
        ...
  slice-02-live-run-view/
    ...
  slice-11-cross-cutting-components/
    ...
```

## Convergence rule

A slice is converged when all three personas return `new_feedback: []` in the same iteration. Capped slices (4 iterations reached without convergence) ship `CONVERGED_AT_CAP.md` and the orchestrator surfaces them for human review.

## Re-export policy

Per the brief, re-run Claude Design with the same slice prompt plus a delta paragraph when:

- A new route is added to `spec.md`.
- A cross-cutting component is added or renamed.
- A user story changes the layout shape of an existing page.
- The palette needs revisiting (audience feedback, accessibility audit finding).

Re-exports re-converge live to design, not the other way around.
