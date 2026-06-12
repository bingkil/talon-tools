"""Talon tool definitions for Facebook integration."""

from __future__ import annotations

import logging
from typing import Any

from talon_tools import Tool, ToolResult
from talon_tools.credentials import CredentialRequirement, validate

from .client import FBClient
from .parser import format_posts

log = logging.getLogger(__name__)

CREDENTIALS = [
    CredentialRequirement("FB_C_USER", "Facebook c_user cookie"),
    CredentialRequirement("FB_XS", "Facebook xs cookie"),
]


def build_tools(**_kwargs) -> list[Tool]:
    """Return Facebook tools for agent use."""
    validate("facebook", CREDENTIALS)

    _client: FBClient | None = None

    def _get_client() -> FBClient:
        nonlocal _client
        if _client is None:
            _client = FBClient()
        return _client

    async def feed_handler(args: dict[str, Any]) -> ToolResult:
        count = int(args.get("count", 10))
        try:
            posts = await _get_client().get_feed(count=count)
            return ToolResult(content=format_posts(posts[:count]))
        except Exception as e:
            log.exception("fb_get_feed failed")
            return ToolResult(content=f"Error fetching Facebook feed: {e}", is_error=True)

    return [
        Tool(
            name="fb_get_feed",
            description=(
                "Fetch the Facebook news feed. Returns recent posts from friends "
                "and pages you follow, with author, text, timestamp, and URL. "
                "Uses a headless browser — may take 10-20 seconds."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of posts to fetch (default 10, max ~20).",
                        "default": 10,
                    },
                },
                "required": [],
            },
            handler=feed_handler,
        ),
    ]
