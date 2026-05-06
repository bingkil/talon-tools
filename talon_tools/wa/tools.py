"""WhatsApp tool definitions for LLM agents — wraps wacli CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from talon_tools import Tool, ToolResult
from .client import WacliClient


def build_tools(store_dir: Path | None = None, **kwargs: Any) -> list[Tool]:
    """Return WhatsApp tools backed by wacli.

    Args:
        store_dir: wacli store directory (default: ~/.wacli).
    """

    client = WacliClient(store_dir=store_dir)

    # ------------------------------------------------------------------
    # send_whatsapp_message
    # ------------------------------------------------------------------
    async def handle_send(args: dict[str, Any]) -> ToolResult:
        to = args.get("to", "").strip()
        message = args.get("message", "").strip()
        reply_to = args.get("reply_to", "").strip() or None
        mentions = args.get("mentions") or None
        result = await client.send_text(to, message, reply_to=reply_to, mentions=mentions)
        return ToolResult(content=result, is_error=result.startswith("Error"))

    # ------------------------------------------------------------------
    # send_whatsapp_file
    # ------------------------------------------------------------------
    async def handle_send_file(args: dict[str, Any]) -> ToolResult:
        to = args.get("to", "").strip()
        file_path = args.get("file_path", "").strip()
        caption = args.get("caption", "").strip() or None
        result = await client.send_file(to, file_path, caption)
        return ToolResult(content=result, is_error=result.startswith("Error"))

    # ------------------------------------------------------------------
    # send_whatsapp_reaction
    # ------------------------------------------------------------------
    async def handle_react(args: dict[str, Any]) -> ToolResult:
        to = args.get("to", "").strip()
        msg_id = args.get("message_id", "").strip()
        reaction = args.get("reaction", "👍").strip()
        result = await client.send_reaction(to, msg_id, reaction)
        return ToolResult(content=result, is_error=result.startswith("Error"))

    # ------------------------------------------------------------------
    # list_whatsapp_chats
    # ------------------------------------------------------------------
    async def handle_list_chats(args: dict[str, Any]) -> ToolResult:
        limit = int(args.get("limit", 20))
        query = args.get("query", "").strip() or None
        unread = args.get("unread")
        pinned = args.get("pinned")
        result = await client.list_chats(
            limit=min(limit, 100), query=query, unread=unread, pinned=pinned,
        )
        return ToolResult(content=result)

    # ------------------------------------------------------------------
    # search_whatsapp_messages
    # ------------------------------------------------------------------
    async def handle_search(args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "").strip()
        chat = args.get("chat", "").strip() or None
        limit = int(args.get("limit", 20))
        has_media = args.get("has_media", False)
        after = args.get("after", "").strip() or None
        before = args.get("before", "").strip() or None
        result = await client.search_messages(
            query, chat=chat, limit=min(limit, 50),
            has_media=has_media, after=after, before=before,
        )
        return ToolResult(content=result, is_error=result.startswith("Error"))

    # ------------------------------------------------------------------
    # get_whatsapp_messages
    # ------------------------------------------------------------------
    async def handle_get_messages(args: dict[str, Any]) -> ToolResult:
        chat = args.get("chat", "").strip()
        limit = int(args.get("limit", 20))
        after = args.get("after", "").strip() or None
        before = args.get("before", "").strip() or None
        result = await client.list_messages(
            chat, limit=min(limit, 50), after=after, before=before,
        )
        return ToolResult(content=result, is_error=result.startswith("Error"))

    # ------------------------------------------------------------------
    # get_whatsapp_message_context
    # ------------------------------------------------------------------
    async def handle_context(args: dict[str, Any]) -> ToolResult:
        chat = args.get("chat", "").strip()
        msg_id = args.get("message_id", "").strip()
        n_before = int(args.get("before", 3))
        n_after = int(args.get("after", 3))
        result = await client.message_context(chat, msg_id, before=n_before, after=n_after)
        return ToolResult(content=result, is_error=result.startswith("Error"))

    # ------------------------------------------------------------------
    # search_whatsapp_contacts
    # ------------------------------------------------------------------
    async def handle_contacts(args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "").strip()
        limit = int(args.get("limit", 20))
        result = await client.search_contacts(query, limit=min(limit, 100))
        return ToolResult(content=result, is_error=result.startswith("Error"))

    # ------------------------------------------------------------------
    # list_whatsapp_groups
    # ------------------------------------------------------------------
    async def handle_groups(args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "").strip() or None
        limit = int(args.get("limit", 20))
        result = await client.list_groups(query=query, limit=min(limit, 100))
        return ToolResult(content=result)

    # ------------------------------------------------------------------
    # get_whatsapp_group_info
    # ------------------------------------------------------------------
    async def handle_group_info(args: dict[str, Any]) -> ToolResult:
        jid = args.get("jid", "").strip()
        result = await client.group_info(jid)
        return ToolResult(content=result, is_error=result.startswith("Error"))

    # ------------------------------------------------------------------
    # mark_whatsapp_read
    # ------------------------------------------------------------------
    async def handle_mark_read(args: dict[str, Any]) -> ToolResult:
        chat = args.get("chat", "").strip()
        result = await client.mark_read(chat)
        return ToolResult(content=result, is_error=result.startswith("Error"))

    return [
        Tool(
            name="send_whatsapp_message",
            description=(
                "Send a WhatsApp message to a contact or group. "
                "Recipient can be a phone number (+1234567890), a JID, "
                "or a synced contact/group name. Supports replies and mentions."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient — phone number, JID, or contact name"},
                    "message": {"type": "string", "description": "Message text to send"},
                    "reply_to": {"type": "string", "description": "Message ID to reply/quote (optional)"},
                    "mentions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Phone numbers to @mention (optional)",
                    },
                },
                "required": ["to", "message"],
            },
            handler=handle_send,
        ),
        Tool(
            name="send_whatsapp_file",
            description=(
                "Send a file via WhatsApp (image, video, audio, document). "
                "Max 100 MiB. Supports optional caption."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient — phone number, JID, or contact name"},
                    "file_path": {"type": "string", "description": "Absolute path to the file to send"},
                    "caption": {"type": "string", "description": "Optional caption for the file"},
                },
                "required": ["to", "file_path"],
            },
            handler=handle_send_file,
        ),
        Tool(
            name="send_whatsapp_reaction",
            description="React to a WhatsApp message with an emoji.",
            parameters={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Chat JID or phone number where the message is"},
                    "message_id": {"type": "string", "description": "ID of the message to react to"},
                    "reaction": {"type": "string", "description": "Emoji reaction (default: 👍). Empty string removes reaction."},
                },
                "required": ["to", "message_id"],
            },
            handler=handle_react,
        ),
        Tool(
            name="list_whatsapp_chats",
            description=(
                "List recent WhatsApp chats. Shows names, JIDs, and unread counts. "
                "Filter by unread, pinned, or search by name."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max chats (default 20, max 100)"},
                    "query": {"type": "string", "description": "Filter chats by name"},
                    "unread": {"type": "boolean", "description": "Only show unread chats"},
                    "pinned": {"type": "boolean", "description": "Only show pinned chats"},
                },
            },
            handler=handle_list_chats,
        ),
        Tool(
            name="search_whatsapp_messages",
            description=(
                "Full-text search across WhatsApp messages. "
                "Optionally filter by chat, date range, or media presence."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search text"},
                    "chat": {"type": "string", "description": "Limit search to this chat (JID or name)"},
                    "limit": {"type": "integer", "description": "Max results (default 20, max 50)"},
                    "has_media": {"type": "boolean", "description": "Only messages with attachments"},
                    "after": {"type": "string", "description": "Only after this date (YYYY-MM-DD)"},
                    "before": {"type": "string", "description": "Only before this date (YYYY-MM-DD)"},
                },
                "required": ["query"],
            },
            handler=handle_search,
        ),
        Tool(
            name="get_whatsapp_messages",
            description=(
                "Get recent messages from a specific WhatsApp chat. "
                "Use list_whatsapp_chats to find the chat first."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "chat": {"type": "string", "description": "Chat JID or contact name"},
                    "limit": {"type": "integer", "description": "Max messages (default 20, max 50)"},
                    "after": {"type": "string", "description": "Only after this date (YYYY-MM-DD)"},
                    "before": {"type": "string", "description": "Only before this date (YYYY-MM-DD)"},
                },
                "required": ["chat"],
            },
            handler=handle_get_messages,
        ),
        Tool(
            name="get_whatsapp_message_context",
            description=(
                "Get surrounding messages for context around a specific message. "
                "Useful for understanding a conversation thread."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "chat": {"type": "string", "description": "Chat JID"},
                    "message_id": {"type": "string", "description": "Target message ID"},
                    "before": {"type": "integer", "description": "Messages before (default 3)"},
                    "after": {"type": "integer", "description": "Messages after (default 3)"},
                },
                "required": ["chat", "message_id"],
            },
            handler=handle_context,
        ),
        Tool(
            name="search_whatsapp_contacts",
            description="Search WhatsApp contacts by name, phone number, or JID.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (name, phone, or JID)"},
                    "limit": {"type": "integer", "description": "Max results (default 20, max 100)"},
                },
                "required": ["query"],
            },
            handler=handle_contacts,
        ),
        Tool(
            name="list_whatsapp_groups",
            description="List WhatsApp groups. Optionally filter by name.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Filter groups by name"},
                    "limit": {"type": "integer", "description": "Max results (default 20, max 100)"},
                },
            },
            handler=handle_groups,
        ),
        Tool(
            name="get_whatsapp_group_info",
            description="Get detailed info about a WhatsApp group (members, description, etc).",
            parameters={
                "type": "object",
                "properties": {
                    "jid": {"type": "string", "description": "Group JID (e.g. 123456789@g.us)"},
                },
                "required": ["jid"],
            },
            handler=handle_group_info,
        ),
        Tool(
            name="mark_whatsapp_read",
            description="Mark a WhatsApp chat as read.",
            parameters={
                "type": "object",
                "properties": {
                    "chat": {"type": "string", "description": "Chat JID or contact name"},
                },
                "required": ["chat"],
            },
            handler=handle_mark_read,
        ),
    ]
