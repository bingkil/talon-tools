"""Chrome bookmarks tool definitions for LLM agents."""

from __future__ import annotations

from typing import Any

from talon_tools import Tool, ToolResult
from .bookmarks import read_bookmarks


def build_tools(**_kwargs) -> list[Tool]:
    """Return Chrome bookmarks tools."""

    async def handler(args: dict[str, Any]) -> ToolResult:
        result = read_bookmarks(
            username=args.get("username", ""),
            path=args.get("path", ""),
            folder=args.get("folder", ""),
            query=args.get("query", ""),
            limit=args.get("limit", 50),
        )
        return ToolResult(content=result)

    return [
        Tool(
            name="read_chrome_bookmarks",
            description=(
                "Read Chrome bookmarks from the local filesystem. "
                "Works cross-platform (Windows, macOS, Linux). "
                "Can filter by folder path or search by title/URL."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "OS username (optional — defaults to current user)",
                    },
                    "path": {
                        "type": "string",
                        "description": "Explicit path to Chrome Bookmarks JSON file (overrides username detection)",
                    },
                    "folder": {
                        "type": "string",
                        "description": "Filter to bookmarks within this folder (substring match)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search bookmarks by title or URL (case-insensitive)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max bookmarks to return (default 50)",
                    },
                },
                "required": [],
            },
            handler=handler,
        ),
    ]
