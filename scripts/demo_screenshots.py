"""Drive the cached chromium against the live SPA and screenshot each demo page,
so we verify the exact demo click-path renders before presenting it live."""
from __future__ import annotations

from playwright.sync_api import sync_playwright

CHROME = "/home/ubuntu/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"
BASE = "https://integrity-51-81-34-160.nip.io/app/#"
PAGES = [
    ("verdict", f"{BASE}/verdict/vdt_c849693cac6f"),
    ("dashboard", f"{BASE}/dashboard/run_a5b4f61d3558"),
    ("coevolution", f"{BASE}/coevolution/run_a5b4f61d3558"),
    ("launch", f"{BASE}/launch"),
    ("catalog", f"{BASE}/catalog"),
]

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    for name, url in PAGES:
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)  # let the SPA fetch + render
        out = f"/tmp/demo_{name}.png"
        page.screenshot(path=out, full_page=True)
        # surface a little visible text so we can sanity-check content from the log too
        body = page.inner_text("body")[:300].replace("\n", " ")
        print(f"OK {name}: {out}\n   {body}\n")
    browser.close()
