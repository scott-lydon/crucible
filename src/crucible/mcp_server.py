"""Minimal MCP-style stdio JSON-RPC server exposing `crucible_run`.

Newline-delimited JSON-RPC 2.0 over stdin/stdout, stdlib-only. This lets a coding
agent drive the full loop in `auto` mode. A protocol-complete MCP server (using the
official `mcp` package) is a follow-up; this proves the integration shape and is
callable today.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from . import __version__
from .config import CrucibleConfig
from .runner import run

TOOLS = [
    {
        "name": "crucible_run",
        "description": "Run the Crucible AI red-team loop against an AI agent you own: "
                       "attack, gate, fix (as diffs), and re-evaluate on held-out attacks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "default": "builtin:acmebot"},
                "mode": {"type": "string", "enum": ["approve", "auto"], "default": "auto"},
                "operator_owned": {
                    "type": "boolean",
                    "description": "Attestation that you own/are authorized to test the target.",
                    "default": False,
                },
            },
            "required": ["operator_owned"],
        },
    }
]


def _ok(rid: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def handle(req: dict) -> dict | None:
    method = req.get("method")
    rid = req.get("id")
    if method == "initialize":
        return _ok(rid, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "crucible", "version": __version__},
        })
    if method == "tools/list":
        return _ok(rid, {"tools": TOOLS})
    if method == "tools/call":
        params = req.get("params", {})
        if params.get("name") != "crucible_run":
            return _err(rid, -32601, f"unknown tool: {params.get('name')}")
        args = params.get("arguments", {})
        cfg = CrucibleConfig(
            target=args.get("target", "builtin:acmebot"),
            mode=args.get("mode", "auto"),
            operator_owned=bool(args.get("operator_owned", False)),
            assume_yes=True,
            verbose=False,
        )
        try:
            rec = run(cfg)
        except Exception as e:  # noqa: BLE001 — report errors back over the wire
            return _ok(rid, {"content": [{"type": "text", "text": f"ERROR: {e}"}],
                             "isError": True})
        ev = rec.eval_result
        summary = {
            "findings": len(rec.findings),
            "vulnerabilities": len(rec.vulnerabilities),
            "fixes_applied": sum(1 for c in rec.fixes if c.accepted),
            "held_out_catch_rate": ev.held_out_catch_rate if ev else None,
            "generalization_gap": ev.generalization_gap if ev else None,
            "utility_delta": ev.utility_delta if ev else None,
            "report": rec.report_paths[0] if rec.report_paths else None,
        }
        return _ok(rid, {"content": [{"type": "text", "text": json.dumps(summary)}]})
    if method and method.startswith("notifications/"):
        return None
    return _err(rid, -32601, f"method not found: {method}")


def serve(stdin=sys.stdin, stdout=sys.stdout) -> None:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()


if __name__ == "__main__":
    serve()
