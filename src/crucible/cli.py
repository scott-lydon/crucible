"""Command-line interface."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import ALL_CLASSES, CrucibleConfig, NotAuthorizedError
from .runner import run


def _build_config(args: argparse.Namespace) -> CrucibleConfig:
    return CrucibleConfig(
        target=args.target,
        mode=args.mode,
        classes=[c.strip() for c in args.classes.split(",") if c.strip()],
        seeds=args.seeds,
        operator_owned=args.operator_owned,
        assume_yes=args.assume_yes,
        out_dir=args.out_dir,
        llm=args.llm,
        model=args.model,
        prefer_structural=not args.prompt_only,
        verbose=not args.quiet,
        multi_turn=args.multi_turn,
        max_attacks=args.max_attacks,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="crucible",
        description="Automated AI red-team: break your own AI agent, harden it, prove it.",
    )
    sub = p.add_subparsers(dest="cmd")

    rp = sub.add_parser("run", help="Run the full loop against a target")
    rp.add_argument("--target", default="builtin:acmebot",
                    help="builtin:acmebot or an http(s):// endpoint")
    rp.add_argument("--mode", choices=["approve", "auto"], default="approve")
    rp.add_argument("--classes", default=",".join(ALL_CLASSES))
    rp.add_argument("--seeds", type=int, default=3)
    rp.add_argument("--i-own-this-target", action="store_true", dest="operator_owned",
                    help="REQUIRED attestation: you own / are authorized to test this target")
    rp.add_argument("-y", "--yes", action="store_true", dest="assume_yes",
                    help="non-interactive approval of fixes")
    rp.add_argument("--out", default="runs", dest="out_dir")
    rp.add_argument("--llm", choices=["deterministic", "anthropic", "openrouter"],
                    default="deterministic")
    rp.add_argument("--model", default="claude-sonnet-4-6")
    rp.add_argument("--prompt-only", action="store_true",
                    help="prefer prompt fixes (demonstrates the generalization gap)")
    rp.add_argument("--multi-turn", action="store_true", dest="multi_turn",
                    help="also run a multi-turn (crescendo) attacker (needs an LLM target + attacker)")
    rp.add_argument("--max-attacks", type=int, default=0, dest="max_attacks",
                    help="cap library attacks per class (0 = no cap); useful for live LLM cost")
    rp.add_argument("--config", help="load run config from a JSON file (CLI flags still apply)")
    rp.add_argument("--quiet", action="store_true")

    sub.add_parser("demo", help="Run the built-in demo (auto mode, sample target)")
    sub.add_parser("browser-demo",
                   help="Run the full loop through a real browser against the local web test-env")
    ip = sub.add_parser("init", help="Write a starter crucible.json config")
    ip.add_argument("path", nargs="?", default="crucible.json")
    sub.add_parser("verify",
                   help="Measure recall + false-positive rate on the ground-truth target suite")
    sub.add_parser("calibrate-judge",
                   help="Report the jailbreak judge's precision/recall/F1 on a labeled set")
    sub.add_parser("version", help="Print version")

    args = p.parse_args(argv)

    if args.cmd is None:
        p.print_help()
        return 1
    if args.cmd == "version":
        print(__version__)
        return 0
    if args.cmd == "init":
        from .config import write_config_template
        write_config_template(args.path)
        print(f"wrote {args.path}")
        return 0
    if args.cmd == "verify":
        from .verify import run_suite
        res = run_suite()
        for name, m in res["targets"].items():
            print(f"  {name:16} recall={m['recall']:.0%}  FPR={m['false_positive_rate']:.0%}  "
                  f"found={m['found']}")
        print(f"\nmacro recall={res['macro_recall']:.0%}  "
              f"macro FPR={res['macro_false_positive_rate']:.0%}")
        return 0
    if args.cmd == "calibrate-judge":
        from .calibration import calibrate, keyword_judge
        m = calibrate(keyword_judge)
        print(f"keyword judge — precision={m['precision']:.0%} recall={m['recall']:.0%} "
              f"f1={m['f1']:.0%}  (tp={m['tp']} fp={m['fp']} tn={m['tn']} fn={m['fn']}, n={m['n']})")
        return 0

    server = None
    if args.cmd == "demo":
        cfg = CrucibleConfig(target="builtin:acmebot", mode="auto",
                             operator_owned=True, assume_yes=True)
    elif args.cmd == "browser-demo":
        from .testenv import serve_background
        server, url = serve_background()
        print(f"▶ test-env vulnerable chatbot live at {url} (driving it via headless Chromium)")
        cfg = CrucibleConfig(target=f"browser:{url}", mode="auto", operator_owned=True,
                             assume_yes=True, seeds=1, out_dir="runs-browser")
    elif getattr(args, "config", None):
        from .config import config_from_file
        cfg = config_from_file(args.config)
        cfg.operator_owned = cfg.operator_owned or args.operator_owned
        cfg.assume_yes = cfg.assume_yes or args.assume_yes
        cfg.verbose = not args.quiet
    else:
        cfg = _build_config(args)

    try:
        rec = run(cfg)
    except NotAuthorizedError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 2
    finally:
        if server is not None:
            server.shutdown()

    ev = rec.eval_result
    md = rec.report_paths[0] if rec.report_paths else "(none)"
    if ev:
        print(f"\n✓ done — held-out catch rate {ev.held_out_catch_rate:.0%}, "
              f"generalization gap {ev.generalization_gap:+.0%}, "
              f"utility {ev.utility_delta:+.0%}. Report: {md}")
    else:
        print(f"\n✓ done — {len(rec.findings)} finding(s). Report: {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
