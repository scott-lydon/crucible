"""Browser adapter — drive a real web chat UI through Chromium (Playwright).

This reaches targets with no API (UI-only chatbots), and reads the bot reply AND
tool calls from the *rendered DOM* — observing what the UI actually shows rather
than trusting a JSON field. Deterministic, no LLM key required.

The optional `browser-use` Agent (LLM-driven navigation of unknown UIs) plugs in
behind `autonomous=True`; it needs an API key and is not exercised offline.
"""

from __future__ import annotations

import glob
import json
import os
import urllib.request
from typing import Any

from .models import Response, ToolCall

_LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]


def find_chrome() -> str | None:
    """Locate a Chromium binary. Honors $CRUCIBLE_CHROME, else the Playwright cache."""
    env = os.environ.get("CRUCIBLE_CHROME")
    if env and os.path.exists(env):
        return env
    patterns = [
        os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome"),
        "/root/.cache/ms-playwright/chromium-*/chrome-linux*/chrome",
    ]
    for pat in patterns:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None  # let Playwright resolve its default


class _Pool:
    """One Chromium for the whole process; pages are created per adapter."""

    _pw = None
    _browser = None

    @classmethod
    def browser(cls):
        if cls._browser is None:
            from playwright.sync_api import sync_playwright  # lazy: optional dep

            cls._pw = sync_playwright().start()
            cls._browser = cls._pw.chromium.launch(
                headless=True, executable_path=find_chrome(), args=_LAUNCH_ARGS
            )
            import atexit

            atexit.register(cls.close)
        return cls._browser

    @classmethod
    def close(cls):
        try:
            if cls._browser:
                cls._browser.close()
            if cls._pw:
                cls._pw.stop()
        except Exception:  # noqa: BLE001
            pass
        cls._browser = None
        cls._pw = None


class BrowserAdapter:
    """Grey-box adapter over a web chatbot (the test-env app, or any compatible UI)."""

    def __init__(self, url: str, instance: str = "default", timeout_ms: int = 10000):
        self.base = url.rstrip("/")
        self.instance = instance
        self.timeout_ms = timeout_ms
        self._page = None

    def _page_obj(self):
        if self._page is None:
            self._page = _Pool.browser().new_page()
            self._page.goto(f"{self.base}/?id={self.instance}", wait_until="domcontentloaded")
        return self._page

    def send(self, message: str) -> Response:
        page = self._page_obj()
        before = page.eval_on_selector_all(".turn", "els => els.length")
        page.fill("#msg", message)
        page.click("#send")
        page.wait_for_function(
            f"document.querySelectorAll('.turn').length > {before}", timeout=self.timeout_ms
        )
        turn = page.query_selector_all(".turn")[-1]
        text_el = turn.query_selector(".bot-msg")
        text = text_el.inner_text() if text_el else ""
        tool_calls: list[ToolCall] = []
        for tc in turn.query_selector_all(".tool-call"):  # read side effects from the DOM
            name = tc.get_attribute("data-tool") or ""
            amt = tc.get_attribute("data-amount")
            args: dict[str, Any] = {}
            if amt:
                try:
                    args["amount"] = float(amt)
                except ValueError:
                    pass
            tool_calls.append(ToolCall(name=name, args=args))
        return Response(text=text, tool_calls=tool_calls)

    def get_config(self) -> dict[str, Any] | None:
        try:
            with urllib.request.urlopen(  # noqa: S310 (local test endpoint)
                f"{self.base}/admin/config?id={self.instance}", timeout=10
            ) as r:
                return json.loads(r.read().decode())
        except Exception:  # noqa: BLE001
            return None

    def clone_with_config(self, patch: dict[str, Any]) -> "BrowserAdapter | None":
        try:
            data = json.dumps({"base": self.instance, "patch": patch}).encode()
            req = urllib.request.Request(
                f"{self.base}/admin/clone", data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310
                new_id = json.loads(r.read().decode())["id"]
            return BrowserAdapter(self.base, instance=new_id, timeout_ms=self.timeout_ms)
        except Exception:  # noqa: BLE001
            return None
