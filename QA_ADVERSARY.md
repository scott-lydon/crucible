# QA_ADVERSARY

Project-specific brief for the `vouch` sub-agent (`~/.claude/agents/vouch.md`). The agent reads this file on every invocation and treats it as the authoritative override on its generic playbook.

If this file ever reverts to the verbatim template, the sub-agent silently runs the generic playbook and the project loses its targeted Quality Assurance (QA) coverage. The grep in the project governance docs catches that drift.

## 1. Project name and repo path

- Repo path on disk: `<repo-root>`
- GitHub: `https://github.com/scott-lydon/crucible`

## 2. Base branch for diff

Default base: `main`. Run against `main..HEAD` unless an explicit slice branch is being graded, in which case run against `main..<slice-branch>`.

## 3. Test runner command

The canonical command, run from the repo root:

```bash
pytest -xvs \
  --cov=modules --cov=orchestrator --cov=shared \
  --cov-report=term-missing \
  --cov-fail-under=80
```

Per-slice subset commands are listed in `tasks.md` under each slice's "Done criteria for `vouch`" line. Run that subset first; if it passes, run the full suite.

## 4. Harness file paths

- Integration tests: `tests/integration/`
- Per-module tests: `modules/<pillar>/tests/`
- Pre-merge check scripts: `scripts/check_module_imports.py`
- Sandbox seal probe: `shared/sandbox/probes/test_seal.py`
- Replay determinism harness: `tests/integration/test_replay_determinism.py`

## 5. Named bug categories (project hard rules)

The sub-agent treats any of the following as a blocking finding, never a "note." Each maps to a rule in `constitution.md` or a hard rule inherited from `~/.claude/CLAUDE.md`.

1. **Faked or reused data presented as fresh.** Any sample value where a real measurement could exist. Maps to `constitution.md` section 5 and the global "NO MOCK / STUB / FAKE / REUSED DATA" rule.
2. **Producer container reachable to verification artifacts.** Any path by which the producer can read `held_out_tests`, `differential_runs`, the spec resolver, or any oracle internal. Maps to `constitution.md` section 3.
3. **An oracle's reasoning swallowed in the audit trace.** Audit trace must carry the per-oracle reason verbatim; "ok" or "failed" alone is a finding.
4. **A module importing from another module's package.** Maps to `constitution.md` section 2 and the pre-merge check.
5. **`shared/` and `modules/<x>/` in the same pull request.** Pre-merge check rejects it, but `vouch` checks again because the script can be bypassed locally.
6. **Catch-log-continue inside business logic.** Exceptions must propagate up the orchestrator; the loop reports a typed failure to Measure. Catch sites are allowed only at the FastAPI boundary and at sandbox-job entry.
7. **`# type: ignore` without a numbered ticket reference.** Maps to `constitution.md` section 1.
8. **Stale-cache hazard on the dashboard.** Entry HTML must carry `?v=<sha>` and `Cache-Control: no-cache` if filenames are not content-hashed.
9. **Permission prompts overlapping active feature UI.** Maps to the global CLAUDE.md "OS permission prompt timing" rule.
10. **Replay non-determinism.** Any persisted action that produces a different output on replay is a blocking finding; the seed-capture column is missing or wrong.
11. **Halt-certification rule defeated.** Any code path that creates a verdict while `halted=true` is a blocking finding.
12. **Demo-only fallback paths.** No "if no real data is available, show a sample number." If no data, show "Not yet measured." Maps to spec US-10.

## 6. Hot files (from `git diff --name-only HEAD~15..HEAD`)

At slice 0, the only hot files are the foundational artifacts and `website/index.html`. After slice 4, the hot files list is regenerated per session.

The sub-agent regenerates this list itself by running:

```bash
git diff --name-only HEAD~15..HEAD | head -40
```

and treats the top of that list as priority-read files.

## 7. End-to-end pipeline command

The sub-agent verifies the loop runs end to end before declaring `PASS`:

```bash
# from repo root, in a venv with deps installed
python -m crucible.orchestrator.cli demo-run \
  --target fraud \
  --budget 5 \
  --output-dir /tmp/crucible-vouch
```

Expected: exit code 0, non-empty Postgres `verdicts` rows for the run, a non-empty audit trace JSON in `/tmp/crucible-vouch`. If any of those are missing or empty, the sub-agent fails the slice.

## 8. Ignored paths

- `dashboard/node_modules/`
- `dashboard/dist/`
- `artifacts/` (trained model weights; regenerated, not source)
- `website/index.html` (text-only architecture site; reviewed in the same commit as `plan.md`, not separately)
- `_design_bundle/` if it lands later from `claude.ai/design`

## 9. Reports

`vouch` writes its findings to `tests/qa-reports/RUN_REPORT.md` in the project root. The cowork-terminal MCP and the project's normal status checks read only that file; the sub-agent's reasoning trace is not part of the project's persistent state.

## 10. Vouch invocation

From Cowork mode, invocation is via the `claude-code-bridge` Model Context Protocol (MCP) (`mcp__claude-code-bridge__delegate_to_claude_code`). The brief passed in:

- Repo path: `<repo-root>`
- Diff range: `main..<current-branch>`
- Foundational artifacts: `constitution.md`, `spec.md`, `plan.md`, `tasks.md`, this file
- Slice being graded: `<slice-id>` from `tasks.md`
- Ask: "Run vouch with this QA_ADVERSARY brief. Report Adversary Report only."

The sub-agent gets Read, Grep, Glob, and Bash tools only. No Edit, no Write. Any finding it discovers surfaces as a written report or a failing test, never as a silent patch.

## 11. The submit-gate runs at the end of every assignment-touching response

Separate from `vouch`. The submit-gate skill (`~/.claude/skills/submit-gate/SKILL.md`) runs at the end of every response that touches Crucible code, config, or deployment, and ends the response with either `Submit-gate: PASS.` plus evidence or `Submit-gate: FAIL on <line(s)>.` plus continued work in the same turn.

The submit-gate is run by the responding agent, not by `vouch`. `vouch` runs once per slice; submit-gate runs once per response.
