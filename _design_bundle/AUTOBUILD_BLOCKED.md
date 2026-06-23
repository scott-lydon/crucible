# Crucible autobuild — BLOCKED: competing automation on the same project (race still active)

Autonomous fire 2026-06-23 ~13:19Z. The race first documented in
`slice-02-live-run-view/IN_PROGRESS.md` (13:13Z) is STILL active and has
progressed. A human must resolve it before any further autobuild fire can make
progress. No prompt was sent and no HTML/feedback was fabricated this run.

## Live evidence this fire (Pages dropdown, project 64f3247e…)

| Page on server | Last edited | In our manifest? |
|---|---|---|
| slice-06-strategy-catalog | 3m ago | slug belongs to manifest **slice-04**, not 06 |
| slice-05-audit-row-replayer | 8m ago | **NOT in `_slices.json` at all** |
| slice-04-honest-dashboard | 13m ago | slug belongs to manifest **slice-05**, not 04 |
| slice-02-live-run-view | 8h ago | yes (this is our target; untouched) |
| Run Launcher | 9m ago | duplicate, off-manifest naming |
| Run Launcher | 9m ago | duplicate, off-manifest naming |
| slice-01-run-launcher | 9m ago | yes |
| slice-03-verdict-detail | 12h ago | yes |
| Canvas | 2 days ago | scratch |

The 3-to-13-minute-old edits prove a second session is actively cycling RIGHT
NOW. slice-02 has not been touched in 8 hours, so our iter-03 revise still has
not landed.

## The plan divergence (the root problem)

Our manifest `_slices.json` numbering:

- slice-04 = **strategy-catalog**
- slice-05 = **honest-dashboard**
- slice-06 = **blue-patch-diff**

The external session's numbering on the server:

- slice-04 = honest-dashboard  (our 05)
- slice-05 = audit-row-replayer (ours: does not exist)
- slice-06 = strategy-catalog  (our 04)

The two automations disagree on both the order and the membership of the slice
set. They will keep clobbering each other on one shared project chat thread.

## What this fire did / did NOT do

- Verified Chrome MCP + claude.ai logged in (project loaded, composer idle).
- Read the live Pages list (table above).
- Did NOT send the iter-03 revise into slice-02 (would interleave with the
  external session's in-flight request and corrupt both threads).
- Did NOT run the persona critic loop (current slice-02 server content is still
  == v2/v3; re-running would falsely report "no new findings" and trigger a
  bogus CONVERGED).
- Did NOT fabricate any HTML or feedback.

## NEEDED FROM A HUMAN (unchanged from 13:13Z, now more urgent)

1. Find and close the external Claude Design tab/session auto-building
   slices 04/05/06. It is likely a separately scheduled task or a stray tab a
   much earlier run left open. Two automations on one project is the whole bug.
2. Pick the canonical slice plan: either reconcile `_slices.json` to the
   server's slugs (and decide what to do with the off-manifest
   `audit-row-replayer`), or roll back the server's off-plan pages to match the
   manifest. Confirm none of the off-plan pages are the PDF-excluded screens
   (Workspace/Role/Policy, Sealed-spec history).
3. After the race is resolved, the next fire can resume slice-02: send the
   iter-03 revise (the 10 iter-02 items, incl. MRG-12.4 vs MRG-12.6 control-id
   unification) and close the route-spec gaps still missing in the capture
   ("Skip to white-box pass" button, "Not yet measured" empty state, distinct
   empty-state mock).

## Slice status snapshot
- slice-01-run-launcher: CONVERGED_AT_CAP (v4 final). Done.
- slice-02-live-run-view: v3 captured (== v2 design). NOT converged. Blocked.
- slice-03..11: not yet built by THIS manifest's pipeline. slice-03 exists on
  the server and looks complete but has not been captured to disk by us.
