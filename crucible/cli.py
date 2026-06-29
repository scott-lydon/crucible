"""``crucible`` command-line entry point.

Thin argument parsing only: each subcommand dispatches to a handler module whose import
is deferred until the subcommand runs, so ``crucible --help`` and importing the core
never pull FastAPI/uvicorn/Render onto the path. The loop is web-agnostic; this CLI is a
second front-end over the same core, not a rewrite."""

from __future__ import annotations

import argparse
import sys

_STREAM_CHOICES = ("human", "json", "both", "none")


def _add_stream_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--stream", choices=_STREAM_CHOICES, default="human",
        help="terminal output mode: human (pretty), json (raw lines), both, none")
    parser.add_argument(
        "--no-emoji", action="store_true",
        help="render ASCII tags instead of emoji glyphs")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crucible",
        description="Adversarial verification loop from the terminal (no web app required).")
    sub = parser.add_subparsers(dest="command", required=True)

    # --- run ---------------------------------------------------------------
    run = sub.add_parser("run", help="run the full loop against a target")
    run.add_argument("--target", required=True, help="target kind (fraud|code_agent|dummy|...)")
    run.add_argument("--spec", help="path to a sealed-spec YAML file")
    run.add_argument("--rounds", type=int, default=3, help="attack rounds per pass")
    run.add_argument("--max-dollars", type=float, default=5.0, help="per-run budget ceiling")
    run.add_argument("--cap-preview", action="store_true",
                     help="run a short preview and stop for confirmation before a full run")
    run.add_argument("--coevolution", action="store_true", help="run the red/blue duel")
    _add_stream_flags(run)

    # --- replay ------------------------------------------------------------
    replay = sub.add_parser("replay", help="re-verify a stored verdict, assert byte-equality")
    replay.add_argument("run_id")
    replay.add_argument("verdict_id")
    _add_stream_flags(replay)

    # --- report ------------------------------------------------------------
    report = sub.add_parser("report", help="render the static report site from artifact files")
    report.add_argument("--run", help="run id to render")
    report.add_argument("--all", action="store_true", help="render the index over all runs")
    report.add_argument("--open", dest="open_run", help="render and open a run's report site")

    # --- catalog -----------------------------------------------------------
    catalog = sub.add_parser("catalog", help="show the append-only strategy catalog")
    catalog.add_argument("--run", help="limit to one run's catalog.jsonl")

    # --- status ------------------------------------------------------------
    status = sub.add_parser("status", help="list runs and their last known state")
    status.add_argument("--run", help="show one run's status in detail")

    # --- doctor ------------------------------------------------------------
    doctor = sub.add_parser("doctor", help="verify prerequisites for a real run")
    doctor.add_argument("--target", help="check Docker only if this target needs the sandbox")

    # --- eligibility -------------------------------------------------------
    elig = sub.add_parser("eligibility", help="target eligibility pre-flight gate")
    elig_sub = elig.add_subparsers(dest="elig_command", required=True)
    elig_check = elig_sub.add_parser("check", help="classify a target as eligible / ineligible")
    elig_check.add_argument("--target", required=True)
    elig_check.add_argument("--spec")
    elig_check.add_argument("--artifact", help="Shape-1 model artifact (.lgb)")

    # --- suitability -------------------------------------------------------
    suit = sub.add_parser("suitability", help="target suitability advisor (never halts)")
    suit_sub = suit.add_subparsers(dest="suit_command", required=True)
    suit_check = suit_sub.add_parser("check", help="grade a target as IDEAL / WORKABLE / POOR_FIT")
    suit_check.add_argument("--target", required=True)
    suit_check.add_argument("--spec")

    # --- adapter -----------------------------------------------------------
    adapter = sub.add_parser("adapter", help="scaffold a per-project target adapter")
    adapter_sub = adapter.add_subparsers(dest="adapter_command", required=True)
    scaffold = adapter_sub.add_parser("scaffold", help="generate a new adapter module")
    scaffold.add_argument("--project", required=True)
    scaffold.add_argument("--kind", required=True, choices=("shape1", "shape2"))
    scaffold.add_argument("--artifact")
    scaffold.add_argument("--endpoint")
    scaffold.add_argument("--config")
    scaffold.add_argument("--task", default="")

    # --- focus subcommands (5b): same wiring the loop uses --------------------
    oracle = sub.add_parser("oracle", help="run one oracle in isolation")
    oracle_sub = oracle.add_subparsers(dest="oracle_command", required=True)
    oracle_run = oracle_sub.add_parser("run", help="run a named oracle on an output")
    oracle_run.add_argument("--name", required=True)
    oracle_run.add_argument("--target", required=True)
    oracle_run.add_argument("--output", required=True, help="JSON file of the producer output")
    oracle_run.add_argument("--spec", required=True)

    red = sub.add_parser("red", help="run the red agent in isolation")
    red_sub = red.add_subparsers(dest="red_command", required=True)
    red_propose = red_sub.add_parser("propose", help="propose one attack")
    red_propose.add_argument("--target", required=True)
    red_propose.add_argument("--spec", required=True)

    blue = sub.add_parser("blue", help="run the blue agent in isolation")
    blue_sub = blue.add_subparsers(dest="blue_command", required=True)
    blue_propose = blue_sub.add_parser("propose", help="propose a hardening patch")
    blue_propose.add_argument("--target", required=True)
    blue_propose.add_argument("--missed", required=True, help="JSON file of missed attacks")
    blue_propose.add_argument("--spec", required=True)

    verdict = sub.add_parser("verdict", help="aggregate oracle votes into a verdict")
    verdict_sub = verdict.add_subparsers(dest="verdict_command", required=True)
    verdict_agg = verdict_sub.add_parser("aggregate", help="tally a votes file")
    verdict_agg.add_argument("--votes", required=True)

    metrics = sub.add_parser("metrics", help="compute metrics for a run from its trace")
    metrics_sub = metrics.add_subparsers(dest="metrics_command", required=True)
    metrics_compute = metrics_sub.add_parser("compute", help="recompute metrics.json")
    metrics_compute.add_argument("--run", required=True)

    # --- eval (8b) ---------------------------------------------------------
    ev = sub.add_parser("eval", help="run a component eval (dataset + metric + threshold)")
    ev.add_argument("component", help="component name, or 'all'")

    # --- cowork: install the /crucible SKILL.md to ~/.claude/skills/crucible/ ---
    # The [slash-command] install-time extra ships the SKILL.md as package data;
    # this subcommand writes it to the user's Claude skills dir so Cowork picks
    # it up. Refuses to clobber a hand-edited file without --force.
    cowork = sub.add_parser("cowork", help="Cowork / Claude Code integration")
    cowork_sub = cowork.add_subparsers(dest="cowork_command", required=True)
    cowork_install = cowork_sub.add_parser(
        "install-skill",
        help="copy the bundled SKILL.md to ~/.claude/skills/crucible/SKILL.md",
    )
    cowork_install.add_argument(
        "--dest", help="destination path (default ~/.claude/skills/crucible/SKILL.md)")
    cowork_install.add_argument(
        "--force", action="store_true",
        help="overwrite an existing file (default refuses, to protect local edits)")

    # --- demo (10): anti-reward-hacking authenticity observer --------------
    demo = sub.add_parser("demo", help="demo-authenticity observer (certify a captured run)")
    demo_sub = demo.add_subparsers(dest="demo_command", required=True)
    demo_verify = demo_sub.add_parser("verify", help="certify a run was not mocked/reused/staged")
    demo_verify.add_argument("--run", required=True)
    demo_verify.add_argument("--since", type=float, help="capture window start (epoch seconds)")
    demo_verify.add_argument("--until", type=float, help="capture window end (epoch seconds)")
    demo_verify.add_argument("--allow-mock", action="store_true",
                             help="do not require real LLM (for testing the observer itself)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cmd = args.command

    # Logs go to stderr so `crucible run --stream json` keeps stdout a pure event stream.
    from shared.telemetry.log import LazyStderr, configure_logging
    configure_logging(json_output=False, stream=LazyStderr(), cache=False)

    if cmd == "run":
        from crucible.runner import cmd_run
        return cmd_run(args)
    if cmd == "replay":
        from crucible.replay import cmd_replay
        return cmd_replay(args)
    if cmd == "report":
        from crucible.report import cmd_report
        return cmd_report(args)
    if cmd == "catalog":
        from crucible.catalog import cmd_catalog
        return cmd_catalog(args)
    if cmd == "status":
        from crucible.status import cmd_status
        return cmd_status(args)
    if cmd == "doctor":
        from crucible.doctor import cmd_doctor
        return cmd_doctor(args)
    if cmd == "eligibility":
        from crucible.eligibility import cmd_eligibility_check
        return cmd_eligibility_check(args)
    if cmd == "suitability":
        from crucible.suitability import cmd_suitability_check
        return cmd_suitability_check(args)
    if cmd == "adapter":
        from crucible.adapter_scaffold import cmd_adapter_scaffold
        return cmd_adapter_scaffold(args)
    if cmd in ("oracle", "red", "blue", "verdict", "metrics"):
        from crucible.focus import dispatch_focus
        return dispatch_focus(cmd, args)
    if cmd == "eval":
        from crucible.evals import cmd_eval
        return cmd_eval(args)
    if cmd == "demo":
        from crucible.demo_observer import cmd_demo_verify
        return cmd_demo_verify(args)
    if cmd == "cowork":
        if args.cowork_command == "install-skill":
            from crucible.cowork import cmd_cowork_install_skill
            return cmd_cowork_install_skill(args)
        parser.error(f"unknown cowork subcommand {args.cowork_command!r}")

    parser.error(f"unknown command {cmd!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
