"""PR #3 -> main port, Phase F (clean wiring).

F1 the wired registry exposes its eight components and is frozen at startup.
F2 the module-boundary audit is clean for the real tree, and an injected cross-module
   import flips it to a violation (operator-visible, not buried in CI).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from orchestrator.import_audit import import_audit

_EXPECTED = {"targets", "oracles", "aggregator", "red", "blue", "measure", "halt", "spec_compiler"}


def test_f1_wired_components_lists_eight_frozen_fields(client: TestClient) -> None:
    wired = client.get("/admin/wired-components").json()
    assert wired["frozen"] is True
    assert {f["name"] for f in wired["fields"]} == _EXPECTED


def test_f2_real_tree_has_clean_module_boundaries() -> None:
    # The actual modules/ tree imports no other module's package (constitution.md section 2).
    assert import_audit()["clean"] is True


def test_f2_injected_cross_module_import_flips_the_badge(client: TestClient) -> None:
    try:
        client.post("/admin/inject-bad-import?enabled=true")
        bad = client.get("/admin/import-audit").json()
        assert bad["clean"] is False
        assert any("demo-injected" in o for o in bad["offenders"])
    finally:
        client.post("/admin/inject-bad-import?enabled=false")
    assert client.get("/admin/import-audit").json()["clean"] is True
