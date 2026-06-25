"""Sandbox runner for the blue maker's feature-engineering transform.

The blue code-engineering agent supplies ONLY the BODY of
``def engineer(row: dict) -> float``. The harness — never the maker — owns the
I/O: it wraps that body with fixed boilerplate that reads the rows, applies
``engineer`` to each, and prints the resulting list as JSON. The wrapped script
runs in the locked-down Docker sandbox (``shared.sandbox.LocalDockerSandbox``)
over a bounded sample of raw rows.

On ANY failure (broken code, raised exception, wrong-length or non-numeric
output, non-zero exit, timeout) this returns a :class:`TransformError` carrying
the captured message — it NEVER raises into the blue loop. The error is fed back
to the maker so it can repair or form a different hypothesis. The maker is
allowed to fail.
"""

import json
from dataclasses import dataclass

from shared.sandbox.base import Sandbox

# Hard bound on the rows we hand the sandbox per transform (defense + cost).
_MAX_ROWS = 5000
_TIMEOUT_S = 15.0


@dataclass(frozen=True, slots=True)
class TransformError:
    """A failed transform run — carries the captured message for maker feedback."""

    message: str
    stderr: str = ""


def _wrap(engineer_src: str) -> str:
    """Wrap the maker's ``engineer`` body with harness-owned I/O boilerplate.

    The maker controls only the function body. The rows are read as a JSON array
    from STDIN inside the container (NOT embedded in the code string or passed as
    argv — embedding them blows the OS argument-length limit at real data volume,
    E2BIG / "argument list too long"). The command line therefore stays small and
    constant-size regardless of row count. Each row is mapped through ``engineer``
    and the float list is printed as JSON to stdout. ``engineer_src`` is indented
    one level so it becomes the body of the ``def``.
    """
    indented = "\n".join(
        "    " + line if line.strip() else line for line in engineer_src.splitlines()
    )
    return (
        "import json, sys\n"
        "def engineer(row):\n"
        f"{indented}\n"
        "_ROWS = json.loads(sys.stdin.read())\n"
        "_OUT = [float(engineer(r)) for r in _ROWS]\n"
        "print(json.dumps(_OUT))\n"
    )


def run_transform_in_sandbox(
    sandbox: Sandbox, engineer_src: str, rows: list[dict[str, object]]
) -> list[float] | TransformError:
    """Run the maker's transform over ``rows`` in the sandbox; return floats.

    Returns ``list[float]`` aligned to ``rows`` on success, or a
    :class:`TransformError` on any failure (never raises into the loop).
    """
    if len(rows) > _MAX_ROWS:
        return TransformError(
            message=f"refusing to run transform over {len(rows)} rows (cap {_MAX_ROWS})"
        )
    try:
        rows_json = json.dumps(rows)
    except (TypeError, ValueError) as exc:
        return TransformError(message=f"rows are not JSON-serializable: {exc}")

    code = _wrap(engineer_src)
    result = sandbox.run_python(
        code, timeout_s=_TIMEOUT_S, network=False, stdin=rows_json
    )

    if result.timed_out:
        return TransformError(
            message=f"transform timed out after {_TIMEOUT_S}s", stderr=result.stderr
        )
    if result.exit_code != 0:
        return TransformError(
            message=(
                f"transform exited non-zero ({result.exit_code}): "
                f"{(result.stderr or result.stdout).strip()[:1000]}"
            ),
            stderr=result.stderr,
        )

    try:
        parsed = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        return TransformError(
            message=f"transform stdout was not JSON ({exc}): {result.stdout.strip()[:500]}",
            stderr=result.stderr,
        )
    if not isinstance(parsed, list) or len(parsed) != len(rows):
        return TransformError(
            message=(
                "transform output is not a list of the right length "
                f"(got {type(parsed).__name__} len "
                f"{len(parsed) if isinstance(parsed, list) else 'n/a'}, "
                f"expected list len {len(rows)})"
            ),
            stderr=result.stderr,
        )
    values: list[float] = []
    for i, v in enumerate(parsed):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return TransformError(
                message=f"transform output[{i}] is not numeric: {v!r}",
                stderr=result.stderr,
            )
        values.append(float(v))
    return values
