"""cr-e1 done criteria: the Graphite-Meridian design export is served from FastAPI at
/app, every screen carries both the design runtime (support.js) and the live wiring
layer (live.js), and the entry route redirects to the Run Launcher."""

from __future__ import annotations

from fastapi.testclient import TestClient

_SCREENS = (
    "slice-01-run-launcher.dc.html",
    "slice-06-strategy-catalog.dc.html",
    "slice-07-blue-patch-review.dc.html",
    "slice-09-coevolution-curves.dc.html",
    "slice-11-health.dc.html",
)


def test_root_redirects_to_app(client: TestClient) -> None:
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"].rstrip("/").endswith("/app")


def test_dashboard_screens_served_with_both_runtimes(client: TestClient) -> None:
    for screen in _SCREENS:
        resp = client.get(f"/app/{screen}")
        assert resp.status_code == 200, screen
        body = resp.text
        assert "support.js" in body, screen   # design runtime
        assert "live.js" in body, screen       # live wiring


def test_runtime_assets_served(client: TestClient) -> None:
    for asset in ("live.js", "support.js"):
        resp = client.get(f"/app/{asset}")
        assert resp.status_code == 200, asset
        assert len(resp.content) > 1000
