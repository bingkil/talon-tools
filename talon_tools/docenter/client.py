"""Docenter (Zoomin) API client — read-only documentation access.

Supports two auth modes:
1. Session cookie: set DOCENTER_SESSION (from browser _SESSION cookie)
2. JWT (HS256): set DOCENTER_JWT_KEY, DOCENTER_JWT_ISSUER, DOCENTER_USER_EMAIL

Optional: DOCENTER_USER_NAME, DOCENTER_BASE_URL
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx
from bs4 import BeautifulSoup

from talon_tools.credentials import get as cred

log = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://docs-be.niceactimize.com"


class DocenterClient:
    """Async read-only Docenter (Zoomin) API client."""

    def __init__(self) -> None:
        self._base = cred("DOCENTER_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
        self._session_cookie = cred("DOCENTER_SESSION", "")
        self._jwt_key = cred("DOCENTER_JWT_KEY", "")
        self._jwt_issuer = cred("DOCENTER_JWT_ISSUER", "")
        self._user_email = cred("DOCENTER_USER_EMAIL", "")
        self._user_name = cred("DOCENTER_USER_NAME", "Talon Agent")
        self._token: str | None = None
        self._token_exp: int = 0

        if not self._session_cookie and not self._jwt_key:
            raise RuntimeError(
                "Docenter credentials not configured. "
                "Set DOCENTER_SESSION (browser cookie) or "
                "DOCENTER_JWT_KEY + DOCENTER_JWT_ISSUER + DOCENTER_USER_EMAIL."
            )

    def _get_headers(self) -> dict[str, str]:
        """Build auth headers depending on configured mode."""
        headers: dict[str, str] = {
            "Accept": "application/json",
            "Accept-Language": "enus",
            "x-zoomin-product": "portal",
        }
        if self._session_cookie:
            headers["Cookie"] = f"_SESSION={self._session_cookie}"
            headers["Origin"] = "https://docs.niceactimize.com"
        elif self._jwt_key:
            import jwt as pyjwt
            now = int(time.time())
            if not self._token or self._token_exp <= now + 60:
                payload = {
                    "aud": self._base,
                    "iss": self._jwt_issuer,
                    "iat": now,
                    "exp": now + 3600,
                    "sub": self._user_email,
                    "data": {
                        "ZoominRole": "admin",
                        "fullName": self._user_name,
                    },
                }
                self._token = pyjwt.encode(payload, self._jwt_key, algorithm="HS256")
                self._token_exp = now + 3600
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET returning JSON."""
        import httpx
        import json as _json
        import gzip

        url = f"{self._base}{path}"
        headers = self._get_headers()
        # Tell server not to gzip — it lies about Content-Encoding
        headers["Accept-Encoding"] = "identity"
        async with httpx.AsyncClient(timeout=30) as client:
            req = client.build_request("GET", url, params=params, headers=headers)
            resp = await client.send(req, stream=True)
            # Read raw bytes bypassing content-decoding
            raw = b"".join([chunk async for chunk in resp.stream])
            await resp.aclose()
            if resp.status_code >= 400:
                raise RuntimeError(f"Docenter API error {resp.status_code}: {raw[:300].decode(errors='replace')}")
            # Server may claim gzip but send plain JSON — try decompress, fallback to raw
            try:
                data = gzip.decompress(raw)
            except Exception:
                data = raw
            return _json.loads(data)

    # ── Search ────────────────────────────────────────────────────────

    async def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """Full-text search across all documentation."""
        data = await self._get("/api/search", {"q": query, "p": "1", "rpp": str(max_results)})
        groups = data.get("Results", [])
        results = []
        for group in groups:
            leading = group.get("leading_result", {})
            if not leading:
                continue
            results.append({
                "title": leading.get("title", ""),
                "snippet": leading.get("snippet", ""),
                "url": leading.get("url", ""),
                "bundle_id": leading.get("bundle_id", ""),
                "bundle_title": leading.get("publication_title", ""),
                "score": leading.get("score", 0),
                "labels": leading.get("labels_text", "") if isinstance(leading.get("labels_text"), str) else "",
            })
        return results

    # ── Bundle TOC ────────────────────────────────────────────────────

    async def get_bundle_toc(self, bundle_name: str) -> list[dict[str, Any]]:
        """Get table of contents for a documentation bundle."""
        data = await self._get(f"/api/bundle/{bundle_name}/toc", {"language": "enus"})
        if isinstance(data, dict):
            # Error response
            if "error_code" in data:
                raise RuntimeError(f"TOC unavailable for {bundle_name} (error {data['error_code']})")
            entries: list[dict[str, Any]] = []
            for _nav_id, html_content in sorted(data.items()):
                if isinstance(html_content, str):
                    entries.extend(self._parse_toc_html(html_content))
            return entries
        return []

    def _parse_toc_html(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        entries = []
        # Try direct <li> first, then nested in <ul>
        items = soup.find_all("li", recursive=False)
        if not items:
            for ul in soup.find_all("ul", recursive=False):
                items.extend(ul.find_all("li", recursive=False))
        for li in items:
            entry = self._parse_toc_li(li)
            if entry:
                entries.append(entry)
        return entries

    def _parse_toc_li(self, li: Any) -> dict[str, Any] | None:
        link_tag = li.find("a")
        if not link_tag:
            return None
        title = link_tag.get_text(strip=True)
        href = link_tag.get("href", "")
        children = []
        child_ul = li.find("ul", class_="list-links")
        if child_ul:
            for child_li in child_ul.find_all("li", recursive=False):
                child = self._parse_toc_li(child_li)
                if child:
                    children.append(child)
        result: dict[str, Any] = {"title": title, "link": href}
        if children:
            result["children"] = children
        return result

    # ── Page Content ──────────────────────────────────────────────────

    async def get_page(self, bundle_name: str, page_path: str) -> dict[str, Any]:
        """Get content of a documentation page."""
        data = await self._get(f"/api/bundle/{bundle_name}/page/{page_path}")
        html = data.get("topic_html", "")
        text_content = self._extract_text(html)
        breadcrumbs = self._parse_breadcrumbs(data.get("breadcrumbs_html", ""))
        return {
            "title": data.get("title", ""),
            "bundle": bundle_name,
            "bundle_title": data.get("bundle_title", ""),
            "breadcrumbs": breadcrumbs,
            "text_content": text_content,
            "labels": data.get("labels_text", ""),
        }

    async def get_page_by_url(self, page_url: str) -> dict[str, Any]:
        """Get page content from a full Docenter URL."""
        url = page_url.strip()
        base = self._base
        if url.startswith(base):
            url = url[len(base):]
        # Handle both /bundle/X/page/Y and /api/bundle/X/page/Y
        url = url.removeprefix("/api")
        match = re.match(r"/bundle/([^/]+)/page/(.*)", url)
        if not match:
            raise RuntimeError(f"Invalid Docenter URL format: {page_url}")
        return await self.get_page(match.group(1), match.group(2))

    def _extract_text(self, html: str) -> str:
        if not html:
            return ""
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "img"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)

    def _parse_breadcrumbs(self, html: str) -> list[str]:
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        crumbs = [a.get_text(strip=True) for a in soup.find_all("a")]
        active = soup.find("span", class_="active")
        if active:
            crumbs.append(active.get_text(strip=True))
        return crumbs
