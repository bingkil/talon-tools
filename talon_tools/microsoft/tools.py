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
import contextvars
import inspect
from functools import partial
from typing import Any

from talon_tools import Tool, ToolResult
from talon_tools.credentials import CredentialRequirement, validate
from . import outlook, calendar, teams, onedrive

CREDENTIALS = [
    CredentialRequirement("MS_MAIL_TOKEN", "Microsoft Graph mail token cache (MSAL)", required=False),
    CredentialRequirement("MS_CALENDAR_TOKEN", "Microsoft Graph calendar token cache (MSAL)", required=False),
    CredentialRequirement("MS_ONEDRIVE_TOKEN", "Microsoft Graph OneDrive token cache (MSAL)", required=False),
    CredentialRequirement("MS_CLIENT_ID", "Azure AD app client ID", required=False),
    CredentialRequirement("MS_TENANT_ID", "Azure AD tenant ID", required=False),
]


async def _run(fn, **kwargs):
    """Run a sync function in a thread pool, preserving contextvars."""
    loop = asyncio.get_event_loop()
    ctx = contextvars.copy_context()
    return await loop.run_in_executor(None, partial(ctx.run, fn, **kwargs))


def _tool(name: str, description: str, parameters: dict, fn) -> Tool:
    _sig_params = inspect.signature(fn).parameters
    async def handler(args: dict[str, Any]) -> ToolResult:
        filtered = {k: v for k, v in args.items() if k in _sig_params}
        result = await _run(fn, **filtered)
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
                  "filter": {"type": "string", "description": "OData $filter expression. Operators must be lowercase: 'eq', 'and', 'or', 'gt', 'lt'. Filterable fields: subject, from/emailAddress/address, receivedDateTime, isRead, importance, hasAttachments. WRONG: \"from eq 'x@y.com'\" — CORRECT: \"from/emailAddress/address eq 'x@y.com'\". WRONG: \"OR\", \"AND\" — CORRECT: \"or\", \"and\". Keep filters simple; for complex queries use outlook_search instead. Do NOT filter on toRecipients or ccRecipients (unsupported)."},
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
# OneDrive
# ---------------------------------------------------------------------------

def onedrive_tools() -> list[Tool]:
    return [
        _tool("onedrive_list",
              "List files and folders in OneDrive at a given path. Empty path = root.",
              {"type": "object", "properties": {
                  "path": {"type": "string", "description": "Folder path (e.g. 'Documents/Reports'). Empty for root."},
                  "max_results": {"type": "integer", "description": "Max items to return (default 25)"},
              }},
              onedrive.list_files),

        _tool("onedrive_search",
              "Search OneDrive files by name or content.",
              {"type": "object", "properties": {
                  "query": {"type": "string", "description": "Search query (filename or content keywords)"},
                  "max_results": {"type": "integer", "description": "Max results (default 15)"},
              }, "required": ["query"]},
              onedrive.search_files),

        _tool("onedrive_read",
              "Read the text content of a OneDrive file by its item ID. Works for text, CSV, markdown, code files.",
              {"type": "object", "properties": {
                  "item_id": {"type": "string", "description": "OneDrive item ID"},
              }, "required": ["item_id"]},
              onedrive.read_file),

        _tool("onedrive_info",
              "Get detailed metadata for a OneDrive file or folder (size, dates, author, URL).",
              {"type": "object", "properties": {
                  "item_id": {"type": "string", "description": "OneDrive item ID"},
              }, "required": ["item_id"]},
              onedrive.get_info),
    ]


# ---------------------------------------------------------------------------
# Combined
# ---------------------------------------------------------------------------

def outlook_tools() -> list[Tool]:
    return mail_tools() + calendar_tools()


def build_tools(**_kwargs) -> list[Tool]:
    validate("microsoft", CREDENTIALS)
    return mail_tools() + calendar_tools() + teams_tools() + onedrive_tools()
