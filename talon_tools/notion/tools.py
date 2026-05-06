"""Talon tool definitions for Notion integration."""

from __future__ import annotations

import json
import logging
from typing import Any

from talon_tools import Tool, ToolResult

from .client import NotionClient

log = logging.getLogger(__name__)


def _format_search_results(results: list[dict]) -> str:
    """Format search results into readable output."""
    if not results:
        return "No results found."
    lines: list[str] = []
    for r in results:
        obj_type = r.get("object", "unknown")
        obj_id = r.get("id", "")
        title = ""
        if obj_type == "page":
            props = r.get("properties", {})
            title_prop = props.get("title") or props.get("Name") or {}
            if isinstance(title_prop, dict):
                title_arr = title_prop.get("title", [])
                title = "".join(t.get("plain_text", "") for t in title_arr)
        elif obj_type == "database":
            title_arr = r.get("title", [])
            title = "".join(t.get("plain_text", "") for t in title_arr)
        url = r.get("url", "")
        lines.append(f"- [{obj_type}] **{title or '(untitled)'}** — id: `{obj_id}`\n  {url}")
    return "\n".join(lines)


def _format_db_results(results: list[dict]) -> str:
    """Format database query results."""
    if not results:
        return "No entries found."
    lines: list[str] = []
    for r in results:
        obj_id = r.get("id", "")
        props = r.get("properties", {})
        # Extract title
        title = ""
        for prop_name, prop_val in props.items():
            if prop_val.get("type") == "title":
                title_arr = prop_val.get("title", [])
                title = "".join(t.get("plain_text", "") for t in title_arr)
                break
        url = r.get("url", "")
        lines.append(f"- **{title or '(untitled)'}** — id: `{obj_id}`\n  {url}")
    return "\n".join(lines)


def build_tools() -> list[Tool]:
    """Return Notion tools for agent use."""

    _client: NotionClient | None = None

    def _get_client() -> NotionClient:
        nonlocal _client
        if _client is None:
            _client = NotionClient()
        return _client

    async def search_handler(args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "")
        filter_type = args.get("filter_type")
        try:
            results = await _get_client().search(query, filter_type)
            return ToolResult(content=_format_search_results(results))
        except Exception as e:
            log.exception("notion_search failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    async def read_page_handler(args: dict[str, Any]) -> ToolResult:
        page_id = args.get("page_id", "")
        if not page_id:
            return ToolResult(content="Error: page_id is required", is_error=True)
        try:
            resp = await _get_client().read_page_markdown(page_id)
            md = resp.get("markdown", "")
            truncated = resp.get("truncated", False)
            result = md
            if truncated:
                result += "\n\n---\n⚠️ Page was truncated (too large). Some content omitted."
            return ToolResult(content=result)
        except Exception as e:
            log.exception("notion_read_page failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    async def create_page_handler(args: dict[str, Any]) -> ToolResult:
        parent_id = args.get("parent_id", "")
        markdown = args.get("markdown", "")
        title = args.get("title")
        parent_type = args.get("parent_type", "page")
        if not parent_id or not markdown:
            return ToolResult(content="Error: parent_id and markdown are required", is_error=True)
        try:
            resp = await _get_client().create_page(parent_id, markdown, title, parent_type)
            page_id = resp.get("id", "")
            url = resp.get("url", "")
            return ToolResult(content=f"Page created: {url}\nID: {page_id}")
        except Exception as e:
            log.exception("notion_create_page failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    async def update_page_handler(args: dict[str, Any]) -> ToolResult:
        page_id = args.get("page_id", "")
        old_str = args.get("old_str", "")
        new_str = args.get("new_str", "")
        if not page_id or not old_str:
            return ToolResult(content="Error: page_id and old_str are required", is_error=True)
        try:
            resp = await _get_client().update_page_markdown(page_id, old_str, new_str)
            return ToolResult(content="Page updated successfully.")
        except Exception as e:
            log.exception("notion_update_page failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    async def query_database_handler(args: dict[str, Any]) -> ToolResult:
        database_id = args.get("database_id", "")
        if not database_id:
            return ToolResult(content="Error: database_id is required", is_error=True)
        filter_raw = args.get("filter")
        sorts_raw = args.get("sorts")
        # Parse JSON strings if provided
        filter_obj = json.loads(filter_raw) if isinstance(filter_raw, str) else filter_raw
        sorts_obj = json.loads(sorts_raw) if isinstance(sorts_raw, str) else sorts_raw
        try:
            results = await _get_client().query_database(database_id, filter_obj, sorts_obj)
            return ToolResult(content=_format_db_results(results))
        except Exception as e:
            log.exception("notion_query_database failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    return [
        Tool(
            name="notion_search",
            description=(
                "Search Notion for pages and databases by title. "
                "Returns matching items with their IDs and URLs."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (title text to find).",
                    },
                    "filter_type": {
                        "type": "string",
                        "enum": ["page", "database"],
                        "description": "Filter results to only pages or databases. Optional.",
                    },
                },
                "required": ["query"],
            },
            handler=search_handler,
        ),
        Tool(
            name="notion_read_page",
            description=(
                "Read a Notion page's full content as markdown. "
                "Requires the page ID (UUID). Use notion_search to find IDs."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "The Notion page ID (UUID).",
                    },
                },
                "required": ["page_id"],
            },
            handler=read_page_handler,
        ),
        Tool(
            name="notion_create_page",
            description=(
                "Create a new Notion page with markdown content. "
                "The page is created as a child of the specified parent page or database."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "parent_id": {
                        "type": "string",
                        "description": "ID of the parent page or database.",
                    },
                    "markdown": {
                        "type": "string",
                        "description": "Page content in markdown format.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Page title. If omitted, extracted from first # heading.",
                    },
                    "parent_type": {
                        "type": "string",
                        "enum": ["page", "database"],
                        "description": "Whether parent is a page or database. Default: page.",
                    },
                },
                "required": ["parent_id", "markdown"],
            },
            handler=create_page_handler,
        ),
        Tool(
            name="notion_update_page",
            description=(
                "Update a Notion page's content using search-and-replace. "
                "Finds old_str in the page and replaces it with new_str. "
                "Use notion_read_page first to see current content."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "The Notion page ID to update.",
                    },
                    "old_str": {
                        "type": "string",
                        "description": "Exact text to find in the page (case-sensitive).",
                    },
                    "new_str": {
                        "type": "string",
                        "description": "Text to replace old_str with. Empty string to delete.",
                    },
                },
                "required": ["page_id", "old_str", "new_str"],
            },
            handler=update_page_handler,
        ),
        Tool(
            name="notion_query_database",
            description=(
                "Query a Notion database with optional filters and sorts. "
                "Returns matching entries with their titles, IDs, and URLs. "
                "Use notion_search to find database IDs first."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "database_id": {
                        "type": "string",
                        "description": "The Notion database ID.",
                    },
                    "filter": {
                        "type": "object",
                        "description": "Notion filter object. See Notion API docs for filter format.",
                    },
                    "sorts": {
                        "type": "array",
                        "description": "Array of sort objects: [{property, direction}].",
                        "items": {"type": "object"},
                    },
                },
                "required": ["database_id"],
            },
            handler=query_database_handler,
        ),
    ]
