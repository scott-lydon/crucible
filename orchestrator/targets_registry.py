"""API-facing view of the bundled target registry (US-1 input side).

The composition root (``orchestrator.wiring``) is the single source of truth for
which example target adapters exist — it is the one place allowed to import
``examples/``. This module is a thin, ``examples``-free adapter over
``wiring.target_registry()`` that shapes the two read endpoints:

  * ``list_targets()``  -> ``GET /targets`` summaries (no spec body).
  * ``default_spec_yaml(name)`` -> ``GET /targets/{name}/spec`` body (404 on miss).

Keeping this here gives the API one honest place to enumerate targets instead of
a hardcoded list in the frontend, without breaching the import boundary that
reserves ``examples`` access to ``wiring``.
"""

from __future__ import annotations

from typing import cast

from orchestrator import wiring


def list_targets() -> list[dict[str, object]]:
    """The bundled target adapters as ``GET /targets`` summaries (real, not faked)."""
    return [
        {
            "name": name,
            "kind": entry["kind"],
            "model_artifact_ref": entry["model_artifact_ref"],
            "has_default_spec": entry["has_default_spec"],
        }
        for name, entry in wiring.target_registry().items()
    ]


def default_spec_yaml(name: str) -> str:
    """The default sealed-spec YAML for ``name``.

    Raises ``KeyError`` for an unknown target so the API returns an honest 404.
    """
    return cast(str, wiring.target_registry()[name]["default_spec_yaml"])
