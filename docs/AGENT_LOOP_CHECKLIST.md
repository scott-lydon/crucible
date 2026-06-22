# Agent loop checklist (single file, point an autonomous loop at this)

This document is the entry point for any autonomous loop, sub-agent, or human teammate driving Crucible toward the June 29 2026 demo. Pointing a Claude Code session at the repo root and saying "follow `docs/AGENT_LOOP_CHECKLIST.md` to completion" is the intended use.

The checklist is self-contained: every command, every stop condition, every escalation path appears here. The agent never has to ask the human "what's next" except at the explicit checkpoints listed in section 7.

## 1. Pre-flight (run once at session start)

Run the block below verbatim. If any command fails, stop and surface the failure in chat before continuing.

```bash
# 1.1 environment sanity
cd /Users/scottlydon/Desktop/Clutter/iOS/crucible || exit 1
git status                                                    # must be clean
git remote -v | grep -q "labs.gauntletai.com"                 # must exist
git rev-parse --abbrev-ref HEAD                               # report branch
python3.12 --version                                          # must be 3.12+
test -f pyproject.toml || echo "WARNING: slice 0 not yet landed"

# 1.2 read the foundational artifacts in order
cat constitution.md
cat spec.md
cat plan.md
cat tasks.md
cat QA_ADVERSARY.md
cat CONTRIBUTING.md

# 1.3 find the next unchecked slice
grep -nE '^- \[ \] \*\*slice-' tasks.md | head -3
```

The first unchecked slice in `tasks.md` is the next slice to work on.

## 2. Per-slice loop (run for each slice in order)

For every slice, the agent executes these phases. Do not skip phases; the contract relies on them in order.

### 2.1 Read the slice contract

Open `tasks.md`, find the slice. Read every sub-bullet under it. Open `constitution.md` for the rules the slice must respect. Open `spec.md` for the user story the slice advances (named in the slice's owner column). Open `plan.md` for the component(s) the slice touches.

### 2.2 Branch

```bash
git checkout -b <pillar>/slice-<N>-<short-title> main
git pull --rebase origin main
```

Branch naming is enforced by the pre-merge check; see `CONTRIBUTING.md` section 1.

### 2.3 Implement

Work only inside the per-pillar context per `CONTRIBUTING.md` section 6. Concretely the agent's allowed read set for the slice is:

```bash
# the agent's working window for a slice owned by pillar <P>:
shared/
orchestrator/interfaces/
modules/<P>/
tests/integration/test_<P>*.py
```

Modules belonging to other pillars must not be read; their interfaces in `orchestrator/interfaces/` are sufficient.

Hard rule reminders during implementation:

- Modules import only from `shared/` and `orchestrator/interfaces/` (no `from modules.<other>`).
- `shared/types/` changes require a separate branch (do not bundle).
- Every persisted Postgres row carries `created_at`, `pillar`, `dollars_spent`, `seed`, `audit_trace`, `parent_action_id`.
- Every Large Language Model (LLM) call writes a row to `llm_calls`.
- No `# type: ignore` without a numbered ticket reference.
- No mocked data. Real Kaggle dataset, real Claude calls, real Modal jobs. If a dependency is missing, stop and surface it; do not substitute.

### 2.4 Test locally

```bash
ruff check .                       # must be clean
mypy --strict .                    # must be clean
pytest -xvs modules/<P>/tests/     # all green
pytest -xvs tests/integration/     # all green for this slice's integration tests
python scripts/check_module_imports.py   # exit 0
```

If any check fails, fix and re-run. Do not commit broken code.

### 2.5 Update `tasks.md`

Check the slice's sub-bullets in `tasks.md`. The check marks land in the same commit as the slice's code; the diff is the audit trail.

### 2.6 Commit

```bash
git add -A
git commit -m "$(cat <<'EOF'
<type>(<pillar>): slice <N> — <short title>

<two- or three-sentence summary of what shipped>

Closes US-<N> from spec.md.
Touches plan.md section <X>.
Vouch report: tests/qa-reports/RUN_REPORT-slice-<N>.md (pending vouch run).

Assisted-by: Claude
EOF
)"
```

One slice equals one commit. No "WIP" commits on the slice branch; squash locally with `git reset --soft main && git commit -m ...` if multiple commits exist before merge.

### 2.7 Run vouch (fresh-context QA gate)

From Cowork mode, invoke the `claude-code-bridge` Model Context Protocol (MCP) (`mcp__claude-code-bridge__delegate_to_claude_code`). The brief to pass:

```
Repo: /Users/scottlydon/Desktop/Clutter/iOS/crucible
Slice: slice-<N>-<short-title>
Diff range: main..<current-branch>
Read first: constitution.md, spec.md, plan.md, tasks.md, QA_ADVERSARY.md
Ask: Run vouch with this QA_ADVERSARY brief. Report Adversary Report only.
```

From Claude Code, invoke the `vouch` sub-agent directly (`~/.claude/agents/vouch.md`) with the same inputs.

Wait for the report at `tests/qa-reports/RUN_REPORT-slice-<N>.md`.

### 2.8 React to vouch verdict

- **PASS:** continue to 2.9.
- **Blocking findings:** fix all of them in the slice branch, amend the commit, re-run vouch. Do not "loop back later."
- **Two consecutive failed vouches on the same slice:** stop and escalate to the human (see section 8).

### 2.9 Push (dual-push fans out to GitHub plus GitLab)

```bash
git push origin <pillar>/slice-<N>-<short-title>
# verify both remotes:
git ls-remote https://github.com/scott-lydon/crucible.git <branch>
git ls-remote gitlab <branch>
# same sha on both lines → done
```

### 2.10 Open a pull request

```bash
gh pr create \
  --title "<type>(<pillar>): slice <N> — <short title>" \
  --body "$(cat <<'EOF'
## Spec user story
US-<N> from spec.md

## Plan component
plan.md section <X>

## Rubric pillar
<row from spec.md section 5>

## Vouch
tests/qa-reports/RUN_REPORT-slice-<N>.md → PASS
EOF
)"
```

Squash-merge the pull request. One slice equals one commit on `main`.

### 2.11 Run the submit-gate

End the response that contains this slice's work by running `~/.claude/skills/submit-gate/SKILL.md` and printing either `Submit-gate: PASS.` plus evidence or `Submit-gate: FAIL on <line(s)>.` plus continued work in the same turn.

## 3. Slice dependency graph (run order)

Slices 0 to 4 are sequential. Slices 5 onward fan out per `plan.md` section 8.

```
        ┌─ 5 ─ 6 ─ 7 ─ 8 ─ 9 ─ 10  (Pillar 1, Targets and Oracles)
0 ─ 1 ─ 2 ─ 3 ─ 4 ─┼─ 11 ─ 12, 13                (Pillar 2, Red)
        └─ 14                                    (Pillar 3, Blue)
        └─ 15 ─ {16, 17, 18}                     (Pillar 4, Measure)

19 (demo polish, all four converge)
```

If the loop is solo (one agent driving all pillars), walk the graph depth-first: finish a pillar's chain, then the next.

If the loop is parallel (four agents, one per pillar), the four owners launch immediately after slice 4 lands.

## 4. Per-agent context scoping (parallel agent team only)

| Pillar agent | Read set | Forbidden reads |
|---|---|---|
| Targets-and-Oracles | `shared/`, `orchestrator/interfaces/{target,oracle}.py`, `modules/targets/`, `modules/oracles/`, `tests/integration/test_target*.py`, `tests/integration/test_oracle*.py` | other modules |
| Red | `shared/`, `orchestrator/interfaces/red.py`, `modules/red/`, `tests/integration/test_red*.py` | other modules |
| Blue | `shared/`, `orchestrator/interfaces/{blue,measure}.py`, `modules/blue/`, `tests/integration/test_blue*.py` | other modules |
| Measure | `shared/`, `orchestrator/interfaces/measure.py`, `modules/measure/`, `dashboard/`, `tests/integration/test_measure*.py` | other modules |
| Orchestrator | `shared/`, `orchestrator/`, `tests/integration/` (full) | none |

## 5. Cost ceiling per slice

Each slice has a soft dollar ceiling above which the agent stops and asks for human go-ahead. Anthropic spend, not infrastructure spend.

| Slice range | Ceiling per slice |
|---|---|
| 0 to 4 (foundation) | $5 |
| 5 to 10 (oracles) | $20 each |
| 11 to 13 (red) | $30 each (search consumes more tokens) |
| 14 (blue) | $25 |
| 15 to 18 (measure) | $10 each |
| 19 (polish) | $20 |

The agent tracks cost via the Anthropic API headers and the `llm_calls.dollars` column. Crossing the ceiling triggers a "pause and report" event, not a halt; the human approves or sets a new ceiling.

## 6. Cost cap per session

Hard cap per autonomous session: **$60 of Anthropic spend**. At $60, the agent commits in-progress work to a `wip/<branch>` branch, pushes, and stops. The next session resumes from the last committed state.

This cap exists because the global `~/.claude/CLAUDE.md` "Cap processes to ~1 min preview" rule was triggered on 2026-05-29 by a 105-minute, $14 phase-08 conveyor run. The cap here is generous but bounded.

## 7. Human checkpoints (explicit pauses)

The agent pauses and waits for a human at exactly these points:

1. **After slice 4 lands.** Surface "slice 0 to 4 complete, the loop runs end to end with the producer sandbox, Postgres, and the two real target adapters. Recommend the four pillar owners take over for slices 5 to 18, or confirm the loop should continue solo."
2. **After slice 14 lands.** Surface "the blue loop is live; recommend a human review of the proposed patch's training samples before the hardening operation is applied at scale (a LightGBM retrain for the fraud target, a prompt-and-configuration patch for the code-agent target)."
3. **Before slice 19 (demo polish).** Surface "all 18 build slices passed vouch; ready to enter demo polish. Confirm the demo runbook target."
4. **Before any production deploy.** Per the global `~/.claude/CLAUDE.md` "DEPLOY-VERIFY-OR-DIE" rule, the agent prints the deploy verification checklist filled in with the specific commands it ran and waits for the human to verify the dashboard renders.

## 8. Escalation rules (when to stop and ask)

- **Two consecutive vouch failures on the same slice.** Stop. Surface both failure reports plus the agent's hypothesis on why the slice is stuck.
- **A vouch report names a hard rule violation** (faked data, sandbox sealing broken, halt-cert defeated). Stop immediately. These are blocking findings per `QA_ADVERSARY.md` section 5; no in-slice fix; revert the slice and re-plan.
- **The session has spent more than $40 in Anthropic calls without landing a slice.** Stop. The slice is over-scoped; ask for a slice split.
- **A dependency is missing or down** (Kaggle dataset download fails, Modal is unreachable, Anthropic returns 5xx for 10+ minutes). Stop. Do not substitute fake data. Surface the failure.
- **A teammate's interface change request is pending review.** Stop the slice that depends on the change. Work on a different pillar's next slice if available.

## 9. The reset-a-module path

If a pillar owner returns to the codebase and wants to discard the module that landed in their absence:

```bash
# from main, find the slices owned by that pillar:
git log --oneline --grep "^feat(<pillar>):" main

# revert them in reverse order:
git log --oneline --grep "^feat(<pillar>):" main \
  | awk '{print $1}' \
  | xargs -n 1 git revert --no-edit

# delete the implementation directory:
rm -rf modules/<pillar>/

# the orchestrator's interfaces remain unchanged. The platform fails to start
# with "no <Pillar>Agent provider registered" until the pillar owner registers
# their replacement.
```

This is the deletable-module property `constitution.md` section 2 guarantees.

## 10. End-of-session report (the agent writes this every time it stops)

When the agent stops (cost cap, checkpoint, escalation, or normal end), it writes `tests/qa-reports/SESSION-<timestamp>.md` containing:

- Slices completed this session (with commit shas).
- Slices in progress, partial state, and where to resume.
- Cost spent (per slice, total).
- Vouch verdicts (per slice).
- Open blockers and what they need from a human.
- Next slice in the dependency graph and its first checklist line.

The next session reads this file first, before re-running the pre-flight.
