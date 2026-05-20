"""Docenter tool definitions for Talon agents.

Provides read-only access to Actimize documentation (Zoomin-based):
- Hybrid search (keyword + page fetch)
- Full-text search
- Bundle table of contents
- Page content retrieval
"""

from __future__ import annotations

import logging
import re
from typing import Any

from talon_tools import Tool, ToolResult
from talon_tools.credentials import get as cred

from .client import DocenterClient

log = logging.getLogger(__name__)


def build_tools() -> list[Tool]:
    """Return Docenter tools for agent use."""

    _client: DocenterClient | None = None

    def _get_client() -> DocenterClient:
        nonlocal _client
        if _client is None:
            _client = DocenterClient()
        return _client

    async def search_handler(args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "")
        if not query:
            return ToolResult(content="Error: query is required.", is_error=True)
        max_results = int(args.get("max_results") or 10)
        try:
            results = await _get_client().search(query, max_results=max_results)
            if not results:
                return ToolResult(content=f"No documentation found for: {query}")
            lines = [f"**Documentation Search** — {len(results)} results for \"{query}\":\n"]
            for r in results:
                title = r["title"]
                pub = r.get("publication_title", "")
                snippet = r.get("snippet", "")
                link = r.get("link", "")
                lines.append(f"- **{title}** ({pub})")
                if snippet:
                    lines.append(f"  {snippet}")
                if link:
                    lines.append(f"  Link: {link}")
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("docenter_search failed")
            return ToolResult(content=f"Error searching documentation: {e}", is_error=True)

    async def toc_handler(args: dict[str, Any]) -> ToolResult:
        bundle_name = args.get("bundle_name", "")
        if not bundle_name:
            return ToolResult(content="Error: bundle_name is required.", is_error=True)
        try:
            entries = await _get_client().get_bundle_toc(bundle_name)
            if not entries:
                return ToolResult(content=f"No table of contents found for bundle: {bundle_name}")

            def _format_entry(entry: dict, indent: int = 0) -> list[str]:
                prefix = "  " * indent
                lines = [f"{prefix}- {entry['title']} ({entry.get('link', '')})"]
                for child in entry.get("children", []):
                    lines.extend(_format_entry(child, indent + 1))
                return lines

            lines = [f"**Table of Contents — {bundle_name}** ({len(entries)} top-level entries):\n"]
            for entry in entries:
                lines.extend(_format_entry(entry))
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("docenter_toc failed")
            return ToolResult(content=f"Error getting TOC: {e}", is_error=True)

    async def page_handler(args: dict[str, Any]) -> ToolResult:
        bundle_name = args.get("bundle_name", "")
        page_path = args.get("page_path", "")
        if not bundle_name or not page_path:
            return ToolResult(content="Error: bundle_name and page_path are required.", is_error=True)
        try:
            page = await _get_client().get_page(bundle_name, page_path)
            lines = [
                f"# {page['title']}",
                f"**Bundle:** {page['bundle']}",
            ]
            if page.get("breadcrumbs"):
                lines.append(f"**Path:** {' > '.join(page['breadcrumbs'])}")
            if page.get("labels"):
                lines.append(f"**Labels:** {page['labels']}")
            lines.append("")
            lines.append(page.get("text_content", "(no content)"))
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("docenter_page failed")
            return ToolResult(content=f"Error getting page: {e}", is_error=True)

    async def page_url_handler(args: dict[str, Any]) -> ToolResult:
        url = args.get("url", "")
        if not url:
            return ToolResult(content="Error: url is required.", is_error=True)
        try:
            page = await _get_client().get_page_by_url(url)
            lines = [
                f"# {page['title']}",
                f"**Bundle:** {page['bundle']}",
            ]
            if page.get("breadcrumbs"):
                lines.append(f"**Path:** {' > '.join(page['breadcrumbs'])}")
            if page.get("labels"):
                lines.append(f"**Labels:** {page['labels']}")
            lines.append("")
            lines.append(page.get("text_content", "(no content)"))
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("docenter_page_url failed")
            return ToolResult(content=f"Error getting page: {e}", is_error=True)

    async def hybrid_search_handler(args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "")
        if not query:
            return ToolResult(content="Error: query is required.", is_error=True)
        max_results = int(args.get("max_results") or 5)
        fetch_pages = int(args.get("fetch_pages") or 2)

        # Keyword expansion — Docenter does exact token matching, not fuzzy
        _EXPANSIONS = {
            "xsight": "X-Sight",
            "x-sight": "XSight",
            "actone": "ActOne",
            "act one": "ActOne",
            "rcm": "Risk Case Manager",
            "sam": "Suspicious Activity Monitoring",
            "ifm": "Instant Fraud Monitoring",
            "aml": "Anti Money Laundering",
            "wl-x": "Watch List",
            "ftf": "Flow Through Funds",
            "cir": "Circulation of Funds",
            "structuring": "AML-STR Structuring Activity",
            "burst": "AML-BWA Burst Wire Activity",
        }

        def _expand_query(q: str) -> str | None:
            """Return an alternate query with expanded terms, or None if no expansion applies."""
            q_lower = q.lower()
            expanded = q
            changed = False
            for term, alt in _EXPANSIONS.items():
                if term in q_lower and alt.lower() not in q_lower:
                    expanded = re.sub(re.escape(term), alt, expanded, flags=re.IGNORECASE)
                    changed = True
            return expanded if changed else None

        # Step 1: BM25 keyword search with expansion
        try:
            results = await _get_client().search(query, max_results=max_results)
            expanded = _expand_query(query)
            if expanded:
                alt_results = await _get_client().search(expanded, max_results=max_results)
                seen_urls = {r["url"]: r for r in results}
                for r in alt_results:
                    if r["url"] not in seen_urls or r["score"] > seen_urls[r["url"]]["score"]:
                        seen_urls[r["url"]] = r
                results = sorted(seen_urls.values(), key=lambda x: x["score"], reverse=True)[:max_results]
        except Exception as e:
            log.exception("docenter_hybrid_search keyword phase failed")
            return ToolResult(content=f"Error searching documentation: {e}", is_error=True)

        if not results:
            return ToolResult(content=f"No documentation found for: {query}")

        # Step 2: Fetch top N pages for full content
        pages: list[dict[str, Any]] = []
        for r in results[:fetch_pages]:
            try:
                page = await _get_client().get_page_by_url(r["url"])
                pages.append({
                    "title": page.get("title", r["title"]),
                    "bundle": page.get("bundle_title", r.get("bundle_title", "")),
                    "url": r["url"],
                    "content": page.get("text_content", ""),
                })
            except Exception as e:
                log.debug("Failed to fetch page %s: %s", r["url"], e)

        # Step 3: Format output for agent LLM to synthesize
        lines: list[str] = [f"# Documentation Results: \"{query}\"\n"]

        # Full page content (primary material for synthesis)
        for i, p in enumerate(pages, 1):
            lines.append(f"## [{i}] {p['title']}")
            lines.append(f"**Bundle:** {p['bundle']}")
            lines.append(f"**URL:** {p['url']}\n")
            # Cap at 2000 chars per page to stay within reason
            content = p["content"][:2000]
            lines.append(content)
            lines.append("")

        # Remaining matches (titles + snippets only)
        remaining = results[fetch_pages:]
        if remaining:
            lines.append("## Other Matches\n")
            for i, r in enumerate(remaining, len(pages) + 1):
                snippet = r.get("snippet", "").replace("<b>", "**").replace("</b>", "**")
                lines.append(f"**[{i}]** (score: {r['score']}) **{r['title']}**")
                lines.append(f"  Bundle: {r.get('bundle_title', '')} | URL: {r.get('url', '')}")
                if snippet:
                    lines.append(f"  {snippet[:200]}")
                lines.append("")

        return ToolResult(content="\n".join(lines))

    return [
        Tool(
            name="docenter_hybrid_search",
            description=(
                "Search Actimize documentation with keyword expansion and retrieve page content. "
                "Returns full text from top matching pages plus additional ranked matches. "
                "Best for questions about Actimize products, rules, configurations, and procedures."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query or question about Actimize documentation."},
                    "max_results": {"type": "integer", "description": "Max keyword results to return (1-20, default 5)."},
                    "fetch_pages": {"type": "integer", "description": "Number of top results to fetch full page content for (1-5, default 2)."},
                },
                "required": ["query"],
            },
            handler=hybrid_search_handler,
        ),
        Tool(
            name="docenter_search",
            description="Search Actimize documentation (Docenter). Returns titles, snippets, and links.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query text."},
                    "max_results": {"type": "integer", "description": "Maximum results to return (1-50, default 10)."},
                },
                "required": ["query"],
            },
            handler=search_handler,
        ),
        Tool(
            name="docenter_toc",
            description="Get the table of contents for an Actimize documentation bundle. Returns hierarchical page structure.",
            parameters={
                "type": "object",
                "properties": {
                    "bundle_name": {"type": "string", "description": "Documentation bundle name (e.g. 'ActimizeRCM_24.1')."},
                },
                "required": ["bundle_name"],
            },
            handler=toc_handler,
        ),
        Tool(
            name="docenter_page",
            description="Get the content of a specific Actimize documentation page by bundle name and path.",
            parameters={
                "type": "object",
                "properties": {
                    "bundle_name": {"type": "string", "description": "Documentation bundle name."},
                    "page_path": {"type": "string", "description": "Page path within the bundle (e.g. 'Content/Installation/Overview.htm')."},
                },
                "required": ["bundle_name", "page_path"],
            },
            handler=page_handler,
        ),
        Tool(
            name="docenter_page_url",
            description="Get documentation page content from a full Docenter URL.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full Docenter URL (e.g. https://docs-be.niceactimize.com/bundle/BundleName/page/Content/path.htm)."},
                },
                "required": ["url"],
            },
            handler=page_url_handler,
        ),
    ]
