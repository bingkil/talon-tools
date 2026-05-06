"""Web search via DuckDuckGo."""

from __future__ import annotations

import asyncio
from functools import partial

from ddgs import DDGS


def _search_sync(query: str, max_results: int = 5) -> list[dict]:
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


async def search_web(query: str, max_results: int = 5) -> str:
    """Search DuckDuckGo and return formatted results."""
    results = await asyncio.get_event_loop().run_in_executor(
        None, partial(_search_sync, query, max_results)
    )

    if not results:
        return "No results found."

    lines: list[str] = []
    for r in results:
        title = r.get("title", "")
        url = r.get("href", "")
        snippet = r.get("body", "")
        lines.append(f"**{title}**\n{url}\n{snippet}")

    return "\n\n".join(lines)
