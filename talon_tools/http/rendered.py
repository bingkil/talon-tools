"""Fetch rendered web pages using a headless browser (Playwright)."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 8000

_executor = ThreadPoolExecutor(max_workers=2)


def _fetch_sync(url: str, wait_for_selector: str | None, timeout_ms: int) -> str:
    """Run playwright sync API in a worker thread."""
    from playwright.sync_api import sync_playwright

    start = time.monotonic()

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 900},
                )
                page = context.new_page()

                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

                # Give JS a moment to render (don't use networkidle — it hangs on analytics-heavy sites)
                page.wait_for_timeout(2000)

                # If a specific selector was requested, wait for it
                if wait_for_selector:
                    try:
                        page.wait_for_selector(wait_for_selector, timeout=5000)
                    except Exception:
                        pass  # Continue even if selector not found

                # Extract text content — prefer article/main, fall back to body
                text = page.evaluate("""() => {
                    const selectors = ['article', 'main', '[role="main"]', '.post-content', '.article-body'];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim().length > 200) {
                            return el.innerText.trim();
                        }
                    }
                    const body = document.body.cloneNode(true);
                    for (const tag of ['nav', 'header', 'footer', 'script', 'style', 'noscript']) {
                        body.querySelectorAll(tag).forEach(el => el.remove());
                    }
                    return body.innerText.trim();
                }""")

                elapsed_ms = int((time.monotonic() - start) * 1000)
                title = page.title()

            finally:
                browser.close()

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        error_msg = str(e)
        if "net::ERR_" in error_msg or "Timeout" in error_msg:
            return f"FAILED ({elapsed_ms}ms): Could not load page — {error_msg}\nURL: {url}"
        if "Executable doesn't exist" in error_msg:
            return "ERROR: Playwright browsers not installed. Run: playwright install chromium"
        return f"ERROR ({elapsed_ms}ms): {type(e).__name__}: {error_msg}\nURL: {url}"

    if not text:
        return f"Page loaded but no text content extracted ({elapsed_ms}ms).\nTitle: {title}\nURL: {url}"

    # Clean up excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    # Truncate
    truncated = len(text) > MAX_CONTENT_CHARS
    if truncated:
        text = text[:MAX_CONTENT_CHARS]

    lines = [f"Title: {title}", f"URL: {url}", f"Time: {elapsed_ms}ms", ""]
    lines.append(text)
    if truncated:
        lines.append("\n... (truncated)")

    return "\n".join(lines)


async def web_fetch_rendered(
    url: str,
    wait_for_selector: str | None = None,
    timeout_ms: int = 15000,
) -> str:
    """Fetch a page with full JS rendering and return cleaned text content.

    Uses sync Playwright in a thread to avoid async event loop issues on Windows.

    Args:
        url: Full URL to fetch.
        wait_for_selector: Optional CSS selector to wait for before extracting.
        timeout_ms: Navigation timeout in milliseconds (default 15s).
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor, _fetch_sync, url, wait_for_selector, timeout_ms
    )
