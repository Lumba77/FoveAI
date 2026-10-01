"""
web_agent_bridge.py — Jen's real browser.

A persistent headless Chromium session she can drive via <self:browse> tags:
navigate, read, click, type, scroll, screenshot — with a persistent profile
(cookies survive across sessions) and domain guardrails.

Sync Playwright can't run inside the agent's asyncio loop, so the browser
lives on a dedicated thread with its own event loop; all public methods are
synchronous and safe to call from either context.

Env:
    FOVEAI_BROWSE_ENABLED=1        master switch (default on)
    FOVEAI_BROWSE_HEADLESS=0       show the window (debug)
    FOVEAI_BROWSE_WHITELIST        comma domains — if set, ONLY these allowed
    FOVEAI_BROWSE_BLACKLIST        comma domains — appended to built-in blocks
    FOVEAI_BROWSE_MAX_TEXT         chars of page text returned (default 6000)

Vision: the "look" action screenshots and, if a vision callable was injected
(set_vision_callable / agent_state.vision_callable), describes the image —
the mmproj path to sight. Without it, look returns the screenshot path.
"""

import asyncio
import logging
import os
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

FoveAI_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
SESSION_DIR = os.path.join(FoveAI_ROOT, "Backend", "data", "web_session")
SHOT_DIR = os.path.join(FoveAI_ROOT, "Backend", "data", "web_screenshots")

_ENABLED = os.environ.get("FOVEAI_BROWSE_ENABLED", "1") != "0"
_HEADLESS = os.environ.get("FOVEAI_BROWSE_HEADLESS", "1") != "0"
_MAX_TEXT = int(os.environ.get("FOVEAI_BROWSE_MAX_TEXT", "6000"))
_NAV_TIMEOUT = 20000
_CALL_TIMEOUT = 45

# Built-in guardrails: no financial transactions, no account signup flows.
_BLOCK_DOMAINS = [
    "paypal",
    "stripe.",
    "wise.",
    "coinbase",
    "binance",
    "bank",
    "netbank",
    "checkout.",
] + [
    d.strip()
    for d in os.environ.get("FOVEAI_BROWSE_BLACKLIST", "").split(",")
    if d.strip()
]
_BLOCK_PATHS = ["/checkout", "/payment", "/purchase", "/signup", "/register"]
_WHITELIST = [
    d.strip()
    for d in os.environ.get("FOVEAI_BROWSE_WHITELIST", "").split(",")
    if d.strip()
]


def _domain_allowed(url: str) -> str | None:
    """Return None if allowed, else a reason string."""
    try:
        p = urlparse(url)
    except Exception:
        return "unparseable URL"
    if p.scheme not in ("http", "https"):
        return "only http(s) URLs"
    host = (p.hostname or "").lower()
    if _WHITELIST and not any(w in host for w in _WHITELIST):
        return "domain not in whitelist"
    if any(b in host for b in _BLOCK_DOMAINS):
        return "blocked domain (financial/transactional guardrail)"
    path = (p.path or "").lower()
    if any(b in path for b in _BLOCK_PATHS):
        return "blocked path (transaction/signup guardrail)"
    return None


def _extract_text_js() -> str:
    return """(() => {
        const el = document.querySelector('article, main, [role=main]') || document.body;
        let t = el.innerText || '';
        return t.replace(/\\n{3,}/g, '\\n\\n').trim();
    })()"""


class WebAgentBridge:
    """Singleton bridge — one persistent browser shared by all callers."""

    _instance: Optional["WebAgentBridge"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._pw = None
        self._ctx = None
        self._page = None
        self._vision_callable: Callable[[str], str] | None = None
        self._last_used = 0.0

    @classmethod
    def instance(cls) -> "WebAgentBridge":
        with cls._lock:
            if cls._instance is None:
                cls._instance = WebAgentBridge()
            return cls._instance

    def set_vision_callable(self, fn: Callable[[str], str]):
        self._vision_callable = fn

    # ── thread/loop plumbing ──────────────────────────────────────────────
    def _ensure_loop(self):
        if self._loop and self._loop.is_running():
            return
        ready = threading.Event()

        def _run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            ready.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=_run, daemon=True, name="web-agent")
        self._thread.start()
        ready.wait(5)

    def _run(self, coro) -> Any:
        self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=_CALL_TIMEOUT)

    # ── browser lifecycle ─────────────────────────────────────────────────
    async def _ensure_page(self):
        if self._page and not self._page.is_closed():
            return self._page
        from playwright.async_api import async_playwright

        if not self._pw:
            self._pw = await async_playwright().start()
        if not self._ctx:
            os.makedirs(SESSION_DIR, exist_ok=True)
            self._ctx = await self._pw.chromium.launch_persistent_context(
                user_data_dir=SESSION_DIR,
                headless=_HEADLESS,
                viewport={"width": 1280, "height": 900},
                args=["--disable-blink-features=AutomationControlled"],
            )
        self._page = (
            self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()
        )
        return self._page

    async def _snapshot(self, page) -> dict[str, Any]:
        text = await page.evaluate(_extract_text_js())
        links = await page.evaluate(
            """() => Array.from(document.querySelectorAll('a[href]'))
                .slice(0, 30).map(a => ({t: (a.innerText||'').trim().slice(0,60), h: a.href}))
                .filter(l => l.t)"""
        )
        return {
            "url": page.url,
            "title": await page.title(),
            "text": text[:_MAX_TEXT],
            "links": links[:15],
        }

    # ── public actions (sync) ─────────────────────────────────────────────
    def browse(
        self, action: str = "read", url: str = "", selector: str = "", text: str = ""
    ) -> dict[str, Any]:
        if not _ENABLED:
            return {"error": "web browsing disabled (FOVEAI_BROWSE_ENABLED=0)"}
        try:
            return self._run(self._browse_async(action, url, selector, text))
        except Exception as e:
            return {"error": str(e)}

    async def _browse_async(
        self, action: str, url: str, selector: str, text: str
    ) -> dict[str, Any]:
        page = await self._ensure_page()
        self._last_used = asyncio.get_event_loop().time()

        if url:
            blocked = _domain_allowed(url)
            if blocked:
                return {"error": f"navigation refused: {blocked}", "url": url}
            await page.goto(url, timeout=_NAV_TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(1200)  # let JS settle

        a = action.lower()
        if a in ("read", "goto", "open"):
            return await self._snapshot(page)
        if a == "click":
            if not selector:
                return {"error": "click needs selector= (css, or text=label)"}
            loc = (
                page.locator(selector).first
                if not selector.startswith("text=")
                else page.get_by_text(selector[5:], exact=False).first
            )
            await loc.click(timeout=8000)
            await page.wait_for_timeout(1200)
            return await self._snapshot(page)
        if a == "type":
            if not selector:
                return {"error": "type needs selector="}
            await page.fill(selector, text)
            return {"typed": len(text), "into": selector}
        if a == "scroll":
            await page.mouse.wheel(0, 900)
            await page.wait_for_timeout(500)
            return await self._snapshot(page)
        if a == "back":
            await page.go_back(timeout=_NAV_TIMEOUT)
            return await self._snapshot(page)
        if a in ("shot", "screenshot", "look"):
            os.makedirs(SHOT_DIR, exist_ok=True)
            name = datetime.now().strftime("%Y%m%d_%H%M%S") + ".png"
            path = os.path.join(SHOT_DIR, name)
            await page.screenshot(path=path, full_page=False)
            out = await self._snapshot(page)
            out["screenshot"] = path
            if a == "look" and self._vision_callable:
                try:
                    out["vision"] = self._vision_callable(path)
                except Exception as e:
                    out["vision_error"] = str(e)
            return out
        return {
            "error": f"unknown action '{action}'",
            "actions": "read|click|type|scroll|back|shot|look",
        }


# Module-level facade for the tag handlers
def web_browse(
    url: str = "", action: str = "read", selector: str = "", text: str = ""
) -> str:
    """Callable signature for agent_state.web_browse_callable.
    Returns a compact text summary for the model."""
    if not _ENABLED:
        return "Web browsing is disabled."
    res = WebAgentBridge.instance().browse(
        action=action, url=url, selector=selector, text=text
    )
    if "error" in res:
        return f"Browse error: {res['error']}"
    parts = [f"PAGE: {res.get('title', '')} — {res.get('url', '')}"]
    if res.get("text"):
        parts.append(res["text"])
    if res.get("links"):
        parts.append(
            "LINKS: " + ", ".join(f"{l['t']} → {l['h']}" for l in res["links"][:10])
        )
    if res.get("screenshot"):
        parts.append(f"[screenshot: {res['screenshot']}]")
    if res.get("vision"):
        parts.append(f"VISION: {res['vision']}")
    if res.get("typed"):
        parts.append(f"[typed {res['typed']} chars into {res['into']}]")
    return "\n".join(parts)
