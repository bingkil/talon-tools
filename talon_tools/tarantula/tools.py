"""
Tarantula — unified web tools.

Framework-agnostic web toolkit: search, fetch, render, generic HTTP, and
Firecrawl. Firecrawl tools (fc_*) require FIRECRAWL_API_KEY or
FIRECRAWL_API_URL in credentials — without a key they return a helpful
error message at call time.

  web_search          DuckDuckGo search (free, unlimited)
  web_fetch           Plain HTTP content fetch (httpx)
  web_fetch_rendered  JS-rendered content (Playwright, optional dep)
  http_request        General-purpose REST API client
  fc_scrape           URL → clean markdown; handles JS, anti-bot, proxies
  fc_search           Web search + full page markdown per result in one call
  fc_map              Discover all URLs on a site instantly
  fc_crawl            Crawl entire site → all pages as markdown
  fc_agent            Autonomous research — describe what you need, no URL required
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any

import httpx

from talon_tools import Tool, ToolResult
from talon_tools.credentials import get as _cred_get

log = logging.getLogger(__name__)

_MAX_FETCH_CHARS = 8000
_MAX_RENDERED_CHARS = 8000


# ---------------------------------------------------------------------------
# Tier 1: DuckDuckGo
# ---------------------------------------------------------------------------

def _ddg_search_sync(query: str, max_results: int) -> list[dict]:
    from ddgs import DDGS
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


async def _ddg_search(query: str, max_results: int = 5) -> str:
    results = await asyncio.to_thread(_ddg_search_sync, query, max_results)
    if not results:
        return "No results found."
    parts = []
    for r in results:
        parts.append(f"**{r.get('title', '')}**\n{r.get('href', '')}\n{r.get('body', '')}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Tier 1: httpx content fetch
# ---------------------------------------------------------------------------

async def _web_fetch(url: str, max_chars: int = _MAX_FETCH_CHARS) -> str:
    """Fetch a URL and return readable text content."""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; TalonBot/1.0)"},
            )
        ct = r.headers.get("content-type", "")
        if "text" not in ct and "json" not in ct:
            return f"Non-text response ({ct}), {len(r.content)} bytes. Use doc_read for binary files."
        text = r.text
        suffix = f"\n\n[...truncated, {len(text)} chars total]" if len(text) > max_chars else ""
        return f"Status: {r.status_code}\n\n{text[:max_chars]}{suffix}"
    except httpx.TimeoutException:
        return f"TIMEOUT fetching {url}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Tier 1: full HTTP request (REST/API client)
# ---------------------------------------------------------------------------

async def _http_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    params: dict | None = None,
    body: dict | None = None,
    form_data: dict | None = None,
    auth_bearer: str | None = None,
    auth_basic: str | None = None,
    timeout: float = 30.0,
    max_response_bytes: int = 4000,
    follow_redirects: bool = True,
) -> str:
    req_headers = dict(headers) if headers else {}
    if auth_bearer:
        req_headers["Authorization"] = f"Bearer {auth_bearer}"
    elif auth_basic:
        req_headers["Authorization"] = "Basic " + base64.b64encode(auth_basic.encode()).decode()
    if body and "Content-Type" not in req_headers:
        req_headers["Content-Type"] = "application/json"

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=follow_redirects) as client:
            response = await client.request(
                method.upper(), url,
                headers=req_headers, params=params,
                json=body or None, data=form_data or None,
            )
        elapsed = int((time.monotonic() - start) * 1000)
        raw = response.content
        sample = raw[:max_response_bytes]
        try:
            body_text = json.dumps(response.json(), indent=2)
            if len(body_text) > max_response_bytes:
                body_text = body_text[:max_response_bytes] + "\n...(truncated)"
        except Exception:
            body_text = sample.decode("utf-8", errors="replace")
            if len(raw) > max_response_bytes:
                body_text += "\n...(truncated)"
        return "\n".join([
            f"Status: {response.status_code} {response.reason_phrase}",
            f"Time: {elapsed}ms  Size: {len(raw)}b",
            "",
            body_text,
        ])
    except httpx.TimeoutException:
        return f"TIMEOUT after {int((time.monotonic() - start) * 1000)}ms"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Tier 1: Playwright rendered fetch (optional dep)
# ---------------------------------------------------------------------------

def _fetch_rendered_sync(url: str, wait_for_selector: str | None, timeout_ms: int) -> str:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2000)
            if wait_for_selector:
                try:
                    page.wait_for_selector(wait_for_selector, timeout=5000)
                except Exception:
                    pass
            text = page.evaluate("""() => {
                for (const s of ['article','main','[role="main"]','.post-content','.article-body']) {
                    const el = document.querySelector(s);
                    if (el && el.innerText.trim().length > 200) return el.innerText.trim();
                }
                const b = document.body.cloneNode(true);
                for (const t of b.querySelectorAll('script,style,nav,footer,header')) t.remove();
                return b.innerText.trim();
            }""")
            suffix = "[...truncated]" if len(text) > _MAX_RENDERED_CHARS else ""
            return text[:_MAX_RENDERED_CHARS] + suffix
        finally:
            browser.close()


async def _fetch_rendered(url: str, wait_for_selector: str | None = None, timeout_ms: int = 15000) -> str:
    try:
        return await asyncio.to_thread(_fetch_rendered_sync, url, wait_for_selector, timeout_ms)
    except ImportError:
        return "Playwright not installed. Run: playwright install chromium"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Tier 2: Firecrawl SDK helpers (all sync → run in thread)
# ---------------------------------------------------------------------------

def _make_fc_app(api_key: str, api_url: str | None = None):
    from firecrawl import Firecrawl
    kwargs: dict[str, Any] = {"api_key": api_key}
    if api_url:
        kwargs["api_url"] = api_url
    return Firecrawl(**kwargs)


def _fc_scrape_sync(app: Any, url: str, fmt: str) -> str:
    result = app.scrape(url, formats=[fmt])
    content = getattr(result, fmt, None) or str(result)
    if content and len(content) > 12000:
        content = content[:12000] + "\n\n[...truncated]"
    return content or f"No {fmt} content returned for {url}"


def _fc_search_sync(app: Any, query: str, limit: int) -> str:
    results = app.search(query, limit=limit)
    items = getattr(results, "data", results) if not isinstance(results, list) else results
    parts = []
    for r in (items if isinstance(items, list) else []):
        title = r.get("title", "") if isinstance(r, dict) else getattr(r, "title", "")
        url = r.get("url", "") if isinstance(r, dict) else getattr(r, "url", "")
        md = (r.get("markdown") or r.get("description", "")) if isinstance(r, dict) else (getattr(r, "markdown", None) or getattr(r, "description", ""))
        if md and len(md) > 3000:
            md = md[:3000] + "\n...(truncated)"
        parts.append(f"## {title}\n{url}\n\n{md}")
    return "\n\n---\n\n".join(parts) if parts else "No results."


def _fc_map_sync(app: Any, url: str, search: str | None) -> str:
    kwargs = {"search": search} if search else {}
    result = app.map(url, **kwargs)
    links = getattr(result, "links", result) if not isinstance(result, list) else result
    lines = []
    for link in (links if isinstance(links, list) else []):
        if isinstance(link, dict):
            lines.append(f"{link.get('url', link)}  {link.get('title', '')}")
        else:
            lines.append(str(link))
    return "\n".join(lines) if lines else "No URLs found."


def _fc_crawl_sync(app: Any, url: str, limit: int) -> str:
    docs = app.crawl(url, limit=limit)
    pages = getattr(docs, "data", docs) if not isinstance(docs, list) else docs
    parts = []
    for p in (pages if isinstance(pages, list) else []):
        if hasattr(p, "metadata"):
            src = getattr(p.metadata, "source_url", None) or (p.metadata.get("sourceURL", "") if isinstance(p.metadata, dict) else "")
        else:
            src = ""
        md = getattr(p, "markdown", str(p))
        if md and len(md) > 2000:
            md = md[:2000] + "\n...(truncated)"
        parts.append(f"### {src}\n\n{md}")
    return "\n\n---\n\n".join(parts) if parts else "No pages crawled."


def _fc_agent_sync(app: Any, prompt: str, model: str, urls: list[str] | None) -> str:
    kwargs: dict[str, Any] = {"model": model}
    if urls:
        kwargs["urls"] = urls
    result = app.agent(prompt=prompt, **kwargs)
    return str(getattr(result, "data", result))


# ---------------------------------------------------------------------------
# Tool builder
# ---------------------------------------------------------------------------

def build_tools(**_kwargs) -> list[Tool]:
    """Build all web tools.

    All 9 tools are always returned. fc_* tools require FIRECRAWL_API_KEY or
    FIRECRAWL_API_URL — without credentials they return an error at call time.
    """
    api_key = _cred_get("FIRECRAWL_API_KEY", "") or None
    api_url = _cred_get("FIRECRAWL_API_URL", "") or None

    fc_app = None
    if api_key or api_url:
        try:
            fc_app = _make_fc_app(api_key or "", api_url)
        except ImportError:
            log.warning(
                "tarantula: firecrawl-py not installed — fc_* tools unavailable. "
                "Run: pip install firecrawl-py"
            )
        except Exception as e:
            log.warning("tarantula: Firecrawl init failed: %s", e)

    # ── handlers ──────────────────────────────────────────────────────────

    async def web_search_handler(args: dict[str, Any]) -> ToolResult:
        return ToolResult(content=await _ddg_search(
            args.get("query", ""), args.get("max_results", 5)
        ))

    async def web_fetch_handler(args: dict[str, Any]) -> ToolResult:
        return ToolResult(content=await _web_fetch(
            args.get("url", ""), args.get("max_chars", _MAX_FETCH_CHARS)
        ))

    async def web_fetch_rendered_handler(args: dict[str, Any]) -> ToolResult:
        return ToolResult(content=await _fetch_rendered(
            args.get("url", ""),
            args.get("wait_for_selector"),
            args.get("timeout_ms", 15000),
        ))

    async def http_request_handler(args: dict[str, Any]) -> ToolResult:
        return ToolResult(content=await _http_request(
            url=args.get("url", ""),
            method=args.get("method", "GET"),
            headers=args.get("headers"),
            params=args.get("params"),
            body=args.get("body"),
            form_data=args.get("form_data"),
            auth_bearer=args.get("auth_bearer"),
            auth_basic=args.get("auth_basic"),
            timeout=args.get("timeout", 30.0),
            max_response_bytes=args.get("max_response_bytes", 4000),
            follow_redirects=args.get("follow_redirects", True),
        ))

    # ── Tier 1 tools ──────────────────────────────────────────────────────

    tools: list[Tool] = [
        Tool(
            name="web_search",
            description=(
                "Search the web using DuckDuckGo. Returns titles, URLs, and snippets. "
                "Free and unlimited. Use for quick factual lookups, current events, verifying URLs."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Number of results (default 5, max 10)"},
                },
                "required": ["query"],
            },
            handler=web_search_handler,
        ),
        Tool(
            name="web_fetch",
            description=(
                "Fetch a URL and return its text content. Use for reading web pages and articles. "
                "If content is empty (JS-heavy site), use web_fetch_rendered or fc_scrape instead."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "max_chars": {"type": "integer", "description": "Max characters to return (default 8000)"},
                },
                "required": ["url"],
            },
            handler=web_fetch_handler,
        ),
        Tool(
            name="web_fetch_rendered",
            description=(
                "Fetch a URL using a headless browser (Playwright). Use when web_fetch returns "
                "empty or minimal content from JavaScript-heavy sites (React/Vue/Angular SPAs). "
                "Slower than web_fetch (~5-15s). Requires: playwright install chromium"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to render and fetch"},
                    "wait_for_selector": {"type": "string", "description": "Optional CSS selector to wait for before extracting"},
                    "timeout_ms": {"type": "integer", "description": "Navigation timeout in ms (default 15000)"},
                },
                "required": ["url"],
            },
            handler=web_fetch_rendered_handler,
        ),
        Tool(
            name="http_request",
            description=(
                "Make an HTTP request to any URL. Use for REST APIs, webhooks, and endpoints "
                "requiring custom headers, authentication, or a request body. "
                "For reading web page content, prefer web_fetch or fc_scrape."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL including scheme (https://...)"},
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
                        "description": "HTTP method. Default: GET",
                    },
                    "headers": {"type": "object", "description": "Request headers as key-value pairs"},
                    "params": {"type": "object", "description": "Query string parameters"},
                    "body": {"type": "object", "description": "JSON request body"},
                    "form_data": {"type": "object", "description": "Form-encoded body"},
                    "auth_bearer": {"type": "string", "description": "Bearer token (added as Authorization header)"},
                    "auth_basic": {"type": "string", "description": "Basic auth as username:password"},
                    "timeout": {"type": "number", "description": "Timeout in seconds (default 30)"},
                    "max_response_bytes": {"type": "integer", "description": "Truncate response to N bytes (default 4000)"},
                    "follow_redirects": {"type": "boolean", "description": "Follow HTTP redirects (default true)"},
                },
                "required": ["url"],
            },
            handler=http_request_handler,
        ),
    ]

    # ── Firecrawl tools (always registered; require FIRECRAWL_API_KEY) ─────

    _NO_KEY = (
        "Firecrawl not configured. "
        "Set FIRECRAWL_API_KEY in flock credentials to enable fc_* tools."
    )

    async def fc_scrape_handler(args: dict[str, Any]) -> ToolResult:
        if fc_app is None:
            return ToolResult(content=_NO_KEY)
        return ToolResult(content=await asyncio.to_thread(
            _fc_scrape_sync, fc_app, args.get("url", ""), args.get("format", "markdown")
        ))

    async def fc_search_handler(args: dict[str, Any]) -> ToolResult:
        if fc_app is None:
            return ToolResult(content=_NO_KEY)
        return ToolResult(content=await asyncio.to_thread(
            _fc_search_sync, fc_app, args.get("query", ""), args.get("limit", 5)
        ))

    async def fc_map_handler(args: dict[str, Any]) -> ToolResult:
        if fc_app is None:
            return ToolResult(content=_NO_KEY)
        return ToolResult(content=await asyncio.to_thread(
            _fc_map_sync, fc_app, args.get("url", ""), args.get("search")
        ))

    async def fc_crawl_handler(args: dict[str, Any]) -> ToolResult:
        if fc_app is None:
            return ToolResult(content=_NO_KEY)
        return ToolResult(content=await asyncio.to_thread(
            _fc_crawl_sync, fc_app, args.get("url", ""), args.get("limit", 20)
        ))

    async def fc_agent_handler(args: dict[str, Any]) -> ToolResult:
        if fc_app is None:
            return ToolResult(content=_NO_KEY)
        return ToolResult(content=await asyncio.to_thread(
            _fc_agent_sync, fc_app,
            args.get("prompt", ""),
            args.get("model", "spark-1-mini"),
            args.get("urls"),
        ))

    tools.extend([
            Tool(
                name="fc_scrape",
                description=(
                    "Scrape a URL using Firecrawl and return clean markdown. "
                    "Handles JavaScript rendering, anti-bot protection, and proxy rotation. "
                    "Preferred over web_fetch for content-heavy or protected pages."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to scrape"},
                        "format": {
                            "type": "string",
                            "enum": ["markdown", "html", "screenshot"],
                            "description": "Output format (default: markdown)",
                        },
                    },
                    "required": ["url"],
                },
                handler=fc_scrape_handler,
            ),
            Tool(
                name="fc_search",
                description=(
                    "Search the web via Firecrawl and return full page markdown per result. "
                    "Unlike web_search (snippets only), returns the actual content of each result page. "
                    "Use when you need to read the pages found, not just get links."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "description": "Results with full content (default 5)"},
                    },
                    "required": ["query"],
                },
                handler=fc_search_handler,
            ),
            Tool(
                name="fc_map",
                description=(
                    "Discover all URLs on a website instantly. "
                    "Filter by keyword (e.g. 'pricing', 'api', 'changelog') to find specific pages. "
                    "Use before fc_crawl to target specific sections."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Root URL of the site to map"},
                        "search": {"type": "string", "description": "Optional keyword to filter URLs by relevance"},
                    },
                    "required": ["url"],
                },
                handler=fc_map_handler,
            ),
            Tool(
                name="fc_crawl",
                description=(
                    "Crawl an entire website and return all pages as markdown. "
                    "Use for full documentation ingestion or site-wide research. "
                    "Use fc_map first to scope to specific sections."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Root URL to start crawling from"},
                        "limit": {"type": "integer", "description": "Max pages to crawl (default 20)"},
                    },
                    "required": ["url"],
                },
                handler=fc_crawl_handler,
            ),
            Tool(
                name="fc_agent",
                description=(
                    "Autonomous web research agent. Describe what you need in plain English — "
                    "no URL required. Searches, navigates, and extracts data automatically. "
                    "Use spark-1-pro for complex multi-site or critical research tasks."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "What to find or research"},
                        "model": {
                            "type": "string",
                            "enum": ["spark-1-mini", "spark-1-pro"],
                            "description": "spark-1-mini (default, fast/cheap) or spark-1-pro (complex research)",
                        },
                        "urls": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional: focus the agent on specific URLs",
                        },
                    },
                    "required": ["prompt"],
                },
                handler=fc_agent_handler,
            ),
        ])

    return tools
