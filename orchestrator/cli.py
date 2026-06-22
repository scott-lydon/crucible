"""Command-line entry point (``crucible`` console script).

``crucible serve`` runs the API; ``crucible demo-run`` drives one run headless (the
headless body fills in with the pillars). Kept thin — orchestration lives in
loop.py."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="crucible")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the FastAPI server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8099)

    sub.add_parser("demo-run", help="drive one run headless (pillars land in later slices)")

    args = parser.parse_args(argv)

    if args.command == "serve":
        import uvicorn

        uvicorn.run("orchestrator.api:app", host=args.host, port=args.port, log_level="info")
        return 0

    if args.command == "demo-run":
        print("demo-run: the headless loop body lands with the pillars (slice 1+).")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
