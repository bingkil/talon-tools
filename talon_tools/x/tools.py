"""Talon tool definitions for X/Twitter integration."""

from __future__ import annotations

import logging
from typing import Any

from talon_tools import Tool, ToolResult

from .client import XClient
from .parser import parse_timeline, parse_tweet_detail, format_tweets

log = logging.getLogger(__name__)


def build_tools() -> list[Tool]:
    """Return X/Twitter tools for agent use."""

    _client: XClient | None = None

    def _get_client() -> XClient:
        nonlocal _client
        if _client is None:
            _client = XClient()
        return _client

    async def timeline_handler(args: dict[str, Any]) -> ToolResult:
        count = args.get("count", 20)
        try:
            raw = await _get_client().get_home_timeline(count=count)
            tweets = parse_timeline(raw)
            return ToolResult(content=format_tweets(tweets))
        except Exception as e:
            log.exception("x_get_timeline failed")
            return ToolResult(content=f"Error fetching timeline: {e}", is_error=True)

    async def search_handler(args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "")
        count = args.get("count", 20)
        if not query:
            return ToolResult(content="query is required", is_error=True)
        try:
            raw = await _get_client().search(query=query, count=count)
            tweets = parse_timeline(raw)
            return ToolResult(content=format_tweets(tweets))
        except Exception as e:
            log.exception("x_search failed")
            return ToolResult(content=f"Error searching tweets: {e}", is_error=True)

    async def tweet_detail_handler(args: dict[str, Any]) -> ToolResult:
        tweet_id = args.get("tweet_id", "")
        if not tweet_id:
            return ToolResult(content="tweet_id is required", is_error=True)
        try:
            raw = await _get_client().get_tweet(tweet_id)
            tweet = parse_tweet_detail(raw)
            if not tweet:
                return ToolResult(content=f"Could not parse tweet {tweet_id}")
            return ToolResult(
                content=(
                    f"**{tweet.author}** (@{tweet.author_handle})\n"
                    f"{tweet.text}\n"
                    f"❤️ {tweet.likes:,} | 🔁 {tweet.retweets:,} | 💬 {tweet.replies:,}\n"
                    f"{tweet.url}"
                )
            )
        except Exception as e:
            log.exception("x_get_tweet failed")
            return ToolResult(content=f"Error fetching tweet: {e}", is_error=True)

    return [
        Tool(
            name="x_get_timeline",
            description=(
                "Fetch the home timeline from X (Twitter). Returns recent tweets "
                "from accounts you follow with text, author, engagement stats, and URLs."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of tweets to fetch (default 20, max 50)",
                    },
                },
                "required": [],
            },
            handler=timeline_handler,
        ),
        Tool(
            name="x_search",
            description=(
                "Search tweets on X (Twitter). Returns matching tweets with text, "
                "author, engagement stats, and URLs."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (supports X search operators like from:, to:, etc.)",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of results (default 20, max 50)",
                    },
                },
                "required": ["query"],
            },
            handler=search_handler,
        ),
        Tool(
            name="x_get_tweet",
            description=(
                "Fetch a single tweet by ID from X (Twitter). Returns full text, "
                "author, engagement stats, and URL."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "tweet_id": {
                        "type": "string",
                        "description": "The tweet ID (numeric string)",
                    },
                },
                "required": ["tweet_id"],
            },
            handler=tweet_detail_handler,
        ),
    ]
