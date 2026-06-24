# Claude Design stub protocol

The single point of truth for how Claude Design stubbed values enter, traverse,
and leave the Crucible codebase. This file defines the contract; the scripts
under `scripts/` implement it; `design/claude-design-brief.md` instructs Claude
Design to honor it; `coding-practices.md` section 4 cites it.

Every identifier in this protocol is prefixed with `CLAUDE_DESIGN_` (or
`claude_design_`) so that any grep for the word `stub` in the repo always
lands next to the words `Claude Design`. The protocol's only scope is the
Claude Design handoff. Other forms of stubbing in the codebase (the research
agent target adapter that ships as a stub per ARCHITECTURE.md, the
`ScriptedLlmClient` test double, the `DUMMY` slice-1 target) are governed by
`coding-practices.md` section 4 and are not part of this protocol.

## Why this exists

Section 4 of `coding-practices.md` forbids presenting fake, stubbed, or
placeholder data as a real measurement. The Claude Design export is the one
place in the pipeline where fake values legitimately exist: every wireframe
ships a happy-state, an empty-state, and an error-state mock with literal
sample numbers in it. Without a deterministic marker, those literal numbers
silently survive the verbatim copy into `dashboard/src/pages/` and look
identical to real measurements once the dashboard is running. This protocol
makes every Claude Design stubbed value syntactically distinct, scriptable,
and impossible to overlook in a diff or a grep.

## The label format (the contract)

Every Claude Design stubbed value is wrapped in this exact textual shape:

```
__CLAUDE_DESIGN_STUB__[<key>|<kind>|<hint>]__<visibleValue>__/CLAUDE_DESIGN_STUB__
```

| Field          | Meaning                                                                 |
|----------------|-------------------------------------------------------------------------|
| `key`          | Dotted identifier the wiring step keys off. Example: `metric.asr`, `runs.list[0].id`. Allowed characters: `A-Za-z0-9_.[]-`. |
| `kind`         | One of `number`, `string`, `percent`, `currency`, `count`, `timestamp`, `array`, `enum`. The wiring step uses this to pick the right hook. |
| `hint`         | Free text naming the data source. Example: `from /metrics`, `from SSE stream`. Allowed characters: anything except `]`. |
| `visibleValue` | What the design displays at design time. Free text up to the closing `__/CLAUDE_DESIGN_STUB__`. |

The canonical regex (lives in `scripts/_claude_design_stub_contract.py`,
single import site):

```python
CLAUDE_DESIGN_STUB_RE = re.compile(
    r"__CLAUDE_DESIGN_STUB__\["
    r"(?P<key>[A-Za-z0-9_.\[\]\-]+)\|"
    r"(?P<kind>number|string|percent|currency|count|timestamp|array|enum)\|"
    r"(?P<hint>[^\]]*)"
    r"\]__"
    r"(?P<value>.*?)"
    r"__/CLAUDE_DESIGN_STUB__",
    flags=re.DOTALL,
)
```

### Worked example

A metrics tile that will eventually read attack-success-rate from `/metrics`
renders, in the Claude Design happy-state mock, as:

```html
<div class="metric-tile">
  <span class="label">Attack success rate</span>
  <span class="value">__CLAUDE_DESIGN_STUB__[metric.asr|percent|from /metrics]__92.3%__/CLAUDE_DESIGN_STUB__</span>
</div>
```

The empty-state mock for the same tile renders as:

```html
<div class="metric-tile empty">
  <span class="label">Attack success rate</span>
  <span class="value">Not yet measured</span>
</div>
```

The empty-state value is real product copy from `coding-practices.md`
section 4, so it carries no Claude Design stub wrapper. Only fabricated
values get the wrapper.

## The three deterministic steps

```
   Claude Design export                    strip step                wire step
+--------------------------+          +-------------------------+   +-----------------+
|  _design_bundle/*.html   |   --->   | dashboard/src/          |-->| live React tree |
|  __CLAUDE_DESIGN_STUB__  |          | CLAUDE_DESIGN_WIRE_ME_UP|   | hook bindings   |
+--------------------------+          +-------------------------+   +-----------------+
                                                  |
                                                  v
                                     _claude_design_stub_manifest.json
                                     (canonical wire-up work list)
```

### Step 1, strip

`scripts/strip_claude_design_stubs.py` walks the directory passed as
`--bundle-dir` (default `_design_bundle/`) and, for every match of
`CLAUDE_DESIGN_STUB_RE`:

1. Replaces the entire
   `__CLAUDE_DESIGN_STUB__[...]__value__/CLAUDE_DESIGN_STUB__` text with
   `CLAUDE_DESIGN_WIRE_ME_UP[<key>|<kind>]`. The hint and the visible value
   are dropped from the file, because they are not needed once the manifest
   has captured them.
2. Records the stub in `_claude_design_stub_manifest.json` at the bundle
   root, with file, line, key, kind, hint, and the original design value.

Run it after every Claude Design re-export, before the verbatim copy into
`dashboard/src/pages/`:

```bash
uv run python scripts/strip_claude_design_stubs.py --bundle-dir _design_bundle/
```

The script is idempotent. Running it twice on a stripped tree produces an
empty diff and the same manifest.

### Step 2, audit

`scripts/audit_claude_design_stubs.py` greps the whole repo for three
categories of finding, each with its own exit code so a continuous-integration
gate can react appropriately.

| Category | What it finds | Exit code | Action |
|----------|---------------|-----------|--------|
| A | `CLAUDE_DESIGN_WIRE_ME_UP[...]` markers anywhere inside `dashboard/src/`. | 1 | Tracks wire-up work in progress. Allowed during a build, blocks the final ship. |
| B | `__CLAUDE_DESIGN_STUB__[...]` markers anywhere in a code path (not in `_design_bundle/`, `design/`, `docs/`, or root Markdown). | 2 | Bug. The strip step was skipped, or someone bypassed it. |
| C | Heuristic indicators of unmarked fake data inside `dashboard/src/` (four-or-more-digit numeric literals in JSX text, dollar amounts, percent literals, ISO 8601 dates, the words `TODO`, `FIXME`, `XXX`, `Lorem`, `sample`, `example` adjacent to numbers). | 3 | Suspect. Requires manual review. |

Run the audit:

```bash
uv run python scripts/audit_claude_design_stubs.py
```

Exit-code conventions let the pre-merge check stay strict without coupling to
file content:

```bash
# Pre-merge gate: any A, B, or C blocks the merge.
uv run python scripts/audit_claude_design_stubs.py || exit 1

# Build-time gate: only B and C block.
uv run python scripts/audit_claude_design_stubs.py
code=$?
if [ "$code" -ge 2 ]; then exit "$code"; fi
```

### Step 3, wire

The wire step is per-route React work, not a script. The procedure:

1. Read `_design_bundle/_claude_design_stub_manifest.json` to enumerate
   every `key` that needs a binding.
2. For each key, write a hook in `dashboard/src/hooks/` whose name matches
   the key (`useMetricAsr`, `useRunHeader`, etc.) that returns either real
   data from the FastAPI backend or the typed "Not yet measured" sentinel
   per `coding-practices.md` section 4.
3. Replace each `CLAUDE_DESIGN_WIRE_ME_UP[<key>|<kind>]` literal in the page
   with a `{hook()}` expression.
4. Re-run the audit. Category A must reach zero before the slice closes.

The manifest is the work list. When category A is empty and categories B and
C stay empty, the slice has no unwired Claude Design stubs left in the
production tree.

## Where Claude Design stubs are allowed to live

| Path                          | Allowed markers     | Why |
|-------------------------------|---------------------|-----|
| `_design_bundle/`             | `__CLAUDE_DESIGN_STUB__[...]` and `CLAUDE_DESIGN_WIRE_ME_UP[...]` | Design export, ignored by the QA adversary per `QA_ADVERSARY.md`. |
| `design/`                     | `__CLAUDE_DESIGN_STUB__[...]` and `CLAUDE_DESIGN_WIRE_ME_UP[...]` | Pre-export prompts and notes, same ignore-path rule. |
| `dashboard/src/pages/`        | `CLAUDE_DESIGN_WIRE_ME_UP[...]` only, during a build | Page tree after the verbatim copy. `__CLAUDE_DESIGN_STUB__` here is a bug. |
| `frontend/`                   | None after the slice closes | Built bundle. Both markers are bugs in a shipped build. |
| Everything else (backend, tests, shared, modules) | None ever | Section 4 of `coding-practices.md` applies without exception. |

The Mock-LLM mode toggle on `/admin/debug` and the `ScriptedLlmClient` in
unit tests are not part of this protocol. They are first-class product
features governed by `coding-practices.md` section 4 paragraph "What 'mock'
means here".

## Continuous-integration gate

Add the audit step to the pre-merge check (`.github/workflows/ci.yml` or the
local pre-commit hook):

```yaml
- name: claude design stub audit
  run: uv run python scripts/audit_claude_design_stubs.py
```

The job fails on any exit code from 1 upward, which holds the line that a
shipped commit carries no unwired Claude Design stubs and no unmarked fake
data.

## Determinism boundary

The audit step is fully deterministic: identical input produces identical
findings. What is **not** deterministic, and cannot be without changing the
input format, is the per-literal classification of "is this finding a real
stub that needs a backend hook, or is it real product copy (a tab label, a
column legend, a threshold annotation)?". That question requires reading
the surrounding HTML, knowing the route inventory, and choosing a
`data-live` key. The audit surfaces the literal; the human (or a future
session of Claude) classifies it.

Two consequences:

1. The audit's exit code 3 list is a triage queue, not an automatic fix
   list. Wiring every flagged literal blindly would tag UI labels with
   non-existent backend keys, breaking the page.
2. To shrink the queue safely, walk the queue slice by slice, decide
   classification per literal, and either (a) add a `data-live` attribute
   plus a wire function for real stubs, or (b) wrap the literal in
   `__CLAUDE_DESIGN_STUB__[label.intent|enum|fixed UI label]__value__/CLAUDE_DESIGN_STUB__`
   to declare it as accepted-product-copy. Both options strip the literal
   from the unwired queue; only option (a) makes it dynamic at runtime.

The per-slice queue with route hints lives at
`/Users/scottlydon/Documents/Claude/Projects/Gauntlet/handoff-claude-design-wireup.md`.

## Re-running the protocol when the design re-exports

`design/claude-design-brief.md` already lists the conditions under which
Claude Design re-runs (new route, new component, palette revisit, layout
change). On every re-run:

1. Re-paste the brief into Claude Design and export.
2. `scripts/strip_claude_design_stubs.py --bundle-dir _design_bundle/` to
   refresh the manifest and the placeholder markers.
3. Verbatim-copy `_design_bundle/` into `dashboard/src/pages/`.
4. `scripts/audit_claude_design_stubs.py` to find new keys that need hooks.
5. Wire the new keys and re-audit until category A returns zero.

The protocol stays the same; only the manifest grows.
