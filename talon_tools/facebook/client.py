"""Headless browser client for Facebook feed reading via Playwright.

Strategy: load Facebook homepage, intercept GraphQL API responses
triggered by scrolling, and combine with initial page data for a
richer feed extraction.
"""

from __future__ import annotations

import asyncio
import logging
import re

from playwright.async_api import async_playwright, Browser, Playwright, Response

from .auth import load_cookies, playwright_cookies
from .parser import parse_feed_html

log = logging.getLogger(__name__)


class FBClient:
    """Playwright-based async client for Facebook. Reuses browser across calls."""

    def __init__(self) -> None:
        self._cookies = playwright_cookies(load_cookies())
        self._pw: Playwright | None = None
        self._browser: Browser | None = None

    async def _ensure_browser(self) -> None:
        if self._browser is None:
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)

    async def get_feed(self, count: int = 10) -> list[dict]:
        """Load Facebook, scroll to trigger GraphQL feed loads, parse all data."""
        await self._ensure_browser()
        ctx = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        await ctx.add_cookies(self._cookies)
        page = await ctx.new_page()

        # Collect all text sources: initial HTML + GraphQL responses
        all_html_chunks: list[str] = []

        async def _on_response(response: Response) -> None:
            if "/api/graphql" not in response.url:
                return
            try:
                body = await response.text()
                # Only keep responses with feed data
                if '"story":{"creation_time"' in body:
                    all_html_chunks.append(body)
                    log.debug("Captured GraphQL feed response: %d bytes", len(body))
            except Exception:
                pass

        page.on("response", _on_response)

        try:
            await page.goto(
                "https://www.facebook.com/",
                wait_until="domcontentloaded",
                timeout=30000,
            )

            if "login" in page.url or "checkpoint" in page.url:
                raise RuntimeError("Facebook redirected to login — cookies expired")

            # Wait for page to settle, then grab initial HTML
            await page.wait_for_timeout(2000)
            initial_html = await page.content()
            all_html_chunks.append(initial_html)
            log.debug("Initial HTML: %d bytes", len(initial_html))

            # Scroll to trigger GraphQL feed loads
            max_scrolls = max(1, count // 5)
            for i in range(max_scrolls):
                await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
                await page.wait_for_timeout(2000)
                log.debug("Scroll %d done", i + 1)

            # Small extra wait for any in-flight responses
            await page.wait_for_timeout(1000)

            # Parse all collected text
            combined = "\n".join(all_html_chunks)
            return parse_feed_html(combined)
        finally:
            await ctx.close()

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
