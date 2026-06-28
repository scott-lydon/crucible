---
name: crucible
description: Run the Crucible adversarial verification loop (red, verify, harden, measure) from the terminal as a slash command. Use when the user types /crucible or asks to verify an AI target (a fraud classifier, a code agent, or a custom adapter) for silently-wrong outputs, to run an eligibility or suitability check, to replay a verdict, or to render a run report. Streams the loop live and returns the run's artifact files (trace.jsonl, metrics.json, report.md) as clickable links.
---

# /crucible

Drives the Crucible CLI (`crucible` / `python -m crucible`) which runs the full
red, verify, harden, measure loop with no web app required. Everything a run does
streams to the terminal and lands in durable artifact files under
`artifacts/runs/<run_id>/`. The terminal stream and the report site are two
renderers of one append-only event log, so nothing on screen can be faked.

## Repo and environment

The CLI lives in the Crucible repo: `/Users/scottlydon/Desktop/Clutter/iOS/crucible`
(branch `main`, package `crucible/`). Use its venv:

```bash
cd /Users/scottlydon/Desktop/Clutter/iOS/crucible && source .venv/bin/activate
```

The base install needs no web server and no Postgres: each run writes a SQLite
database inside its own run dir. Real-LLM runs need the Claude CLI on PATH and the
`CRUCIBLE_REAL_*` flags; the default is free mock LLMs (still real oracles, real
sandbox, real persistence).

## Parsing the user's request

`/crucible <subcommand> ...` maps to the CLI. Common forms:

- `/crucible run code_agent sum-two-ints.yaml --rounds 6`
  -> `crucible run --target code_agent --spec sum-two-ints.yaml --rounds 6`
- `/crucible run fraud` -> `crucible run --target fraud` (built-in demo spec)
- `/crucible doctor code_agent` -> `crucible doctor --target code_agent`
- `/crucible eligibility fraud` -> `crucible eligibility check --target fraud`
- `/crucible suitability agent` -> `crucible suitability check --target agent`
- `/crucible report <run_id>` -> `crucible report --run <run_id>`
- `/crucible replay <run_id> <verdict_id>`

If no `--spec` is given, the CLI compiles a built-in demo spec for the target, so a
first run needs no authoring. Default `--target` set: `fraud`, `code_agent`, `dummy`
(zero-cost, no Docker), plus `agent`.

## Procedure

1. Run `crucible doctor --target <target>` first and surface any red line with its
   exact fix. Docker is required only for code-shaped targets (the producer sandbox);
   a fraud-only run reports Docker as "not required".
2. Run `crucible run --target <target> [--spec <file>] --rounds <n> --max-dollars <d>
   --stream human` **in the foreground** so its stdout flows back through the shell
   tool's result and the user sees every `Tracer.emit` line in chat. The eligibility
   gate runs first and spends nothing; an INELIGIBLE target exits non-zero with the
   reason and fix, never a silent failure. Suitability warns but never halts.
3. When the run ends, surface the run directory and the key artifacts as clickable
   links with `mcp__cowork__present_files` (and always print the plain absolute paths
   too): `report.md`, `metrics.json`, `sr-117.md`, and `trace.jsonl`. Offer
   `crucible report --open <run_id>` to render the static site.

## Streaming the run to chat (default behavior)

The slash command's primary value is the user watching the loop work. Default to a
foreground synchronous invocation so every event lands in chat:

```bash
crucible run --target <target> [--spec <file>] --rounds <n> --max-dollars <d> --stream human
```

The shell tool's stdout is the per-event log. The user reads the run as it happens
(`run_start`, `eligibility_checked`, `spec_sealed`, `red_tactic_proposed`,
`oracle_voted`, `verdict_decided`, `metric_update`, `artifact_written`, `run_end`).
A short fraud run (`--rounds 3`, real Claude judge) finishes in ~75 seconds and the
full event log fits in one tool result, which is the desired behavior.

**Do NOT background a default-shape run.** Backgrounding with `nohup ... &` makes the
events land in `trace.jsonl` on disk but never reach the chat, leaving the user
staring at "I am notified on completion" prose while the run silently finishes.
That was the 2026-06-28 streaming regression; the fix is to keep the run in the
foreground unless the run is genuinely long.

## Long runs (genuinely long: real LLMs + many rounds OR coevolution)

A run is "genuinely long" only when at least one of: `--rounds > 10`, `--coevolution`
is passed, or `--max-dollars > 5.0` against a real-LLM provider. For those, the
foreground tool call may exceed a single turn. In that case AND ONLY IN THAT CASE:

1. Start the run backgrounded:
   `nohup crucible run ... --stream human > /tmp/crucible-<run_id>.log 2>&1 & disown`
2. Surface the first ~5 events (the doctor, eligibility, spec_sealed, run_start) to
   chat by reading the head of the log right after launch.
3. Schedule a follow-up (per the long-wait pattern in `~/.claude/CLAUDE.md`) to
   read the finished `metrics.json` / `report.md` and deliver them rather than
   sitting in a polling loop.
4. Tell the user the run id, the log path (`/tmp/crucible-<run_id>.log`), and the
   artifact directory.

Default-shape runs (`--rounds <= 6`, no coevolution, max-dollars <= 5) are NOT
long. Run them foreground.

## Cost discipline

Default runs are free (mock LLMs). For real-LLM runs pass `--max-dollars` (a hard
ceiling that halts with a clear BudgetExceeded event) and consider `--cap-preview`
(a short preview that stops before the full run). Surface the live spend from the
`metric_update` lines.

## What to return

A short summary: the verdict counts, the headline metrics (white-box catch rate,
undetected-hack rate, spend), and the artifact links. Never invent a number the run
did not write; a blank metric is "Not yet measured", and that is the honest answer.
