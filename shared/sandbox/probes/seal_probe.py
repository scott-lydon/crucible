"""Seal probe: run inside the sandbox to test whether the seal holds.

From inside a sealed (no-network) sandbox, every connection attempt must fail,
so both reachability flags come back False. Run on the host with a network, the
internet flag comes back True, which is the positive control proving the probe
actually detects reachability (a probe that always returned False would make
the seal test a false pass).

Stdlib only, so it runs in a bare `python:3.12-slim` container. Prints one JSON
line: {"postgres_reachable": bool, "internet_reachable": bool}.
"""

from __future__ import annotations

import json
import socket
import sys


def _reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    """True if a TCP connection to host:port opens within the timeout."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> None:
    pg_host = sys.argv[1] if len(sys.argv) > 1 else "host.docker.internal"
    pg_port = int(sys.argv[2]) if len(sys.argv) > 2 else 5434
    report = {
        "postgres_reachable": _reachable(pg_host, pg_port),
        "internet_reachable": _reachable("1.1.1.1", 443),
    }
    print(json.dumps(report))


if __name__ == "__main__":
    main()
