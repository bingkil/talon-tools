"""Web search tool definitions for LLM agents."""

from __future__ import annotations

from typing import Any

from talon_tools import Tool, ToolResult
from .duckduckgo import search_web


def build_tools() -> list[Tool]:
    """Return web search tools."""

    async def handler(args: dict[str, Any]) -> ToolResult:
        result = await search_web(args.get("query", ""), args.get("max_results", 5))
        return ToolResult(content=result)

    return [
        Tool(
            name="web_search",
            description=(
                "Search the web using DuckDuckGo. Returns titles, URLs, and snippets. "
                "Use for current events, facts, prices, weather, etc."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "max_results": {"type": "integer", "description": "Number of results (default 5, max 10)"},
                },
                "required": ["query"],
            },
            handler=handler,
        ),
    ]
