"""
Microsoft Graph tool definitions for LLM agents.

Provides Tool objects for Outlook Mail, Outlook Calendar, and Teams.
Each tool wraps a sync Graph API call and runs it in a thread pool.

Usage:
    from talon_tools.microsoft.tools import build_tools
    tools = build_tools()           # all Microsoft tools
    tools = outlook_tools()         # just Outlook mail + calendar
    tools = teams_tools()           # just Teams
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

from talon_tools import Tool, ToolResult
from . import outlook, calendar, teams


async def _run(fn, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(fn, **kwargs))


def _tool(name: str, description: str, parameters: dict, fn) -> Tool:
    async def handler(args: dict[str, Any]) -> ToolResult:
        result = await _run(fn, **args)
        return ToolResult(content=result)
    return Tool(name=name, description=description, parameters=parameters, handler=handler)


# ---------------------------------------------------------------------------
# Outlook Mail
# ---------------------------------------------------------------------------

def mail_tools() -> list[Tool]:
    return [
        _tool("outlook_inbox",
              "List recent emails in the Outlook inbox. Optionally filter with OData $filter syntax.",
              {"type": "object", "properties": {
                  "max_results": {"type": "integer", "description": "Number of emails to list (default 10)"},
                  "filter": {"type": "string", "description": "OData filter expression (e.g. \"isRead eq false\")"},
              }},
              outlook.list_inbox),

        _tool("outlook_read",
              "Read the full content of an Outlook email by its message ID.",
              {"type": "object", "properties": {
                  "message_id": {"type": "string", "description": "Outlook message ID"},
              }, "required": ["message_id"]},
              outlook.read_message),

        _tool("outlook_search",
              "Search Outlook emails. Uses Microsoft Graph $search — supports natural language and KQL.",
              {"type": "object", "properties": {
                  "query": {"type": "string", "description": "Search query (e.g. 'budget report from:alice')"},
                  "max_results": {"type": "integer", "description": "Max results (default 10)"},
              }, "required": ["query"]},
              outlook.search_messages),
    ]


# ---------------------------------------------------------------------------
# Outlook Calendar
# ---------------------------------------------------------------------------

def calendar_tools() -> list[Tool]:
    return [
        _tool("outlook_calendar_list",
              "List upcoming Outlook calendar events.",
              {"type": "object", "properties": {
                  "max_results": {"type": "integer", "description": "Max events to return (default 10)"},
                  "days_ahead": {"type": "integer", "description": "Look ahead N days (default 7)"},
              }},
              calendar.list_events),

        _tool("outlook_calendar_get",
              "Get full details of an Outlook calendar event by ID.",
              {"type": "object", "properties": {
                  "event_id": {"type": "string", "description": "Calendar event ID"},
              }, "required": ["event_id"]},
              calendar.get_event),
    ]


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

def teams_tools() -> list[Tool]:
    return [
        _tool("teams_list_teams",
              "List Microsoft Teams the user is a member of.",
              {"type": "object", "properties": {}},
              teams.list_teams),

        _tool("teams_list_channels",
              "List channels in a Microsoft Teams team.",
              {"type": "object", "properties": {
                  "team_id": {"type": "string", "description": "Team ID"},
              }, "required": ["team_id"]},
              teams.list_channels),

        _tool("teams_channel_messages",
              "Read recent messages from a Teams channel.",
              {"type": "object", "properties": {
                  "team_id": {"type": "string", "description": "Team ID"},
                  "channel_id": {"type": "string", "description": "Channel ID"},
                  "max_results": {"type": "integer", "description": "Max messages (default 15)"},
              }, "required": ["team_id", "channel_id"]},
              teams.list_channel_messages),

        _tool("teams_list_chats",
              "List recent 1:1 and group chats in Teams.",
              {"type": "object", "properties": {
                  "max_results": {"type": "integer", "description": "Max chats (default 15)"},
              }},
              teams.list_chats),

        _tool("teams_chat_messages",
              "Read recent messages from a Teams 1:1 or group chat.",
              {"type": "object", "properties": {
                  "chat_id": {"type": "string", "description": "Chat ID"},
                  "max_results": {"type": "integer", "description": "Max messages (default 15)"},
              }, "required": ["chat_id"]},
              teams.list_chat_messages),
    ]


# ---------------------------------------------------------------------------
# Combined
# ---------------------------------------------------------------------------

def outlook_tools() -> list[Tool]:
    return mail_tools() + calendar_tools()


def build_tools() -> list[Tool]:
    return mail_tools() + calendar_tools() + teams_tools()
