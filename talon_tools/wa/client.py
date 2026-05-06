"""wacli subprocess wrapper — async client for WhatsApp operations."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_STORE_DIR = Path.home() / ".wacli"


def _find_wacli() -> str:
    """Locate wacli binary on PATH or common install locations."""
    path = shutil.which("wacli")
    if path:
        return path
    # Check common locations
    candidates = [
        Path.home() / ".local" / "bin" / "wacli",
        Path.home() / "go" / "bin" / "wacli",
        Path.home() / "go" / "bin" / "wacli.exe",
        Path.home() / ".local" / "bin" / "wacli.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    raise FileNotFoundError(
        "wacli not found. Install it: https://github.com/openclaw/wacli#install"
    )


async def _run(args: list[str], timeout: float = 30) -> tuple[str, str, int]:
    """Run a wacli command and return (stdout, stderr, returncode)."""
    cmd = [_find_wacli(), "--json", *args]
    log.debug("wacli exec: %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return "", "Command timed out", 1
    return stdout.decode(), stderr.decode(), proc.returncode or 0


class WacliClient:
    """Async wrapper around the wacli CLI."""

    def __init__(self, store_dir: Path | None = None) -> None:
        self._store_dir = store_dir or DEFAULT_STORE_DIR
        self._base_args = ["--store", str(self._store_dir)]

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    async def send_text(
        self,
        to: str,
        message: str,
        reply_to: str | None = None,
        mentions: list[str] | None = None,
    ) -> str:
        """Send a text message with optional reply and mentions."""
        if not to:
            return "Error: recipient is required"
        if not message:
            return "Error: message is required"
        args = [*self._base_args, "send", "text", "--to", to, "--message", message]
        if reply_to:
            args.extend(["--reply-to", reply_to])
        if mentions:
            for m in mentions:
                args.extend(["--mention", m])
        stdout, stderr, rc = await _run(args)
        if rc != 0:
            return f"Error sending message: {stderr.strip() or stdout.strip()}"
        return stdout.strip() or "Message sent."

    async def send_file(
        self, to: str, file_path: str, caption: str | None = None
    ) -> str:
        """Send a file (image/video/audio/document)."""
        if not to:
            return "Error: recipient is required"
        if not file_path:
            return "Error: file_path is required"
        args = [*self._base_args, "send", "file", "--to", to, "--file", file_path]
        if caption:
            args.extend(["--caption", caption])
        stdout, stderr, rc = await _run(args, timeout=60)
        if rc != 0:
            return f"Error sending file: {stderr.strip() or stdout.strip()}"
        return stdout.strip() or "File sent."

    async def send_reaction(self, to: str, msg_id: str, reaction: str = "👍") -> str:
        """React to a message."""
        if not to or not msg_id:
            return "Error: recipient and message ID are required"
        args = [
            *self._base_args, "send", "react",
            "--to", to, "--id", msg_id, "--reaction", reaction,
        ]
        stdout, stderr, rc = await _run(args)
        if rc != 0:
            return f"Error sending reaction: {stderr.strip() or stdout.strip()}"
        return stdout.strip() or "Reaction sent."

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    async def list_messages(
        self,
        chat: str,
        limit: int = 20,
        from_me: bool | None = None,
        after: str | None = None,
        before: str | None = None,
    ) -> str:
        """List messages from a specific chat."""
        if not chat:
            return "Error: chat is required"
        args = [*self._base_args, "messages", "list", "--chat", chat, "--limit", str(limit)]
        if from_me is True:
            args.append("--from-me")
        elif from_me is False:
            args.append("--from-them")
        if after:
            args.extend(["--after", after])
        if before:
            args.extend(["--before", before])
        stdout, stderr, rc = await _run(args, timeout=30)
        if rc != 0:
            return f"Error listing messages: {stderr.strip() or stdout.strip()}"
        return _format_messages(stdout)

    async def search_messages(
        self,
        query: str,
        chat: str | None = None,
        limit: int = 20,
        has_media: bool = False,
        after: str | None = None,
        before: str | None = None,
    ) -> str:
        """Full-text search messages in the local store."""
        if not query:
            return "Error: query is required"
        args = [*self._base_args, "messages", "search", query, "--limit", str(limit)]
        if chat:
            args.extend(["--chat", chat])
        if has_media:
            args.append("--has-media")
        if after:
            args.extend(["--after", after])
        if before:
            args.extend(["--before", before])
        stdout, stderr, rc = await _run(args, timeout=30)
        if rc != 0:
            return f"Error searching messages: {stderr.strip() or stdout.strip()}"
        return _format_messages(stdout)

    async def message_context(self, chat: str, msg_id: str, before: int = 3, after: int = 3) -> str:
        """Get surrounding context for a message."""
        if not chat or not msg_id:
            return "Error: chat and message ID are required"
        args = [
            *self._base_args, "messages", "context",
            "--chat", chat, "--id", msg_id,
            "--before", str(before), "--after", str(after),
        ]
        stdout, stderr, rc = await _run(args, timeout=30)
        if rc != 0:
            return f"Error getting context: {stderr.strip() or stdout.strip()}"
        return _format_messages(stdout)

    # ------------------------------------------------------------------
    # Chats
    # ------------------------------------------------------------------

    async def list_chats(
        self,
        limit: int = 20,
        query: str | None = None,
        unread: bool | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
    ) -> str:
        """List chats with optional filters."""
        args = [*self._base_args, "chats", "list", "--limit", str(limit)]
        if query:
            args.extend(["--query", query])
        if unread is True:
            args.append("--unread")
        if pinned is True:
            args.append("--pinned")
        if archived is True:
            args.append("--archived")
        stdout, stderr, rc = await _run(args)
        if rc != 0:
            return f"Error listing chats: {stderr.strip() or stdout.strip()}"
        return _format_chats(stdout)

    async def mark_read(self, chat: str) -> str:
        """Mark a chat as read."""
        if not chat:
            return "Error: chat is required"
        stdout, stderr, rc = await _run(
            [*self._base_args, "chats", "mark-read", "--chat", chat]
        )
        if rc != 0:
            return f"Error marking read: {stderr.strip() or stdout.strip()}"
        return stdout.strip() or "Chat marked as read."

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------

    async def search_contacts(self, query: str, limit: int = 20) -> str:
        """Search contacts by name, phone, or JID."""
        if not query:
            return "Error: query is required"
        args = [*self._base_args, "contacts", "search", query, "--limit", str(limit)]
        stdout, stderr, rc = await _run(args)
        if rc != 0:
            return f"Error searching contacts: {stderr.strip() or stdout.strip()}"
        return _format_contacts(stdout)

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    async def list_groups(self, query: str | None = None, limit: int = 20) -> str:
        """List WhatsApp groups."""
        args = [*self._base_args, "groups", "list", "--limit", str(limit)]
        if query:
            args.extend(["--query", query])
        stdout, stderr, rc = await _run(args)
        if rc != 0:
            return f"Error listing groups: {stderr.strip() or stdout.strip()}"
        return _format_groups(stdout)

    async def group_info(self, jid: str) -> str:
        """Get detailed info about a group."""
        if not jid:
            return "Error: group JID is required"
        stdout, stderr, rc = await _run(
            [*self._base_args, "groups", "info", "--jid", jid]
        )
        if rc != 0:
            return f"Error getting group info: {stderr.strip() or stdout.strip()}"
        return stdout.strip() or "No info available."

    # ------------------------------------------------------------------
    # Presence
    # ------------------------------------------------------------------

    async def send_typing(self, to: str) -> str:
        """Send typing indicator."""
        if not to:
            return "Error: recipient is required"
        stdout, stderr, rc = await _run(
            [*self._base_args, "presence", "typing", "--to", to]
        )
        if rc != 0:
            return f"Error sending typing: {stderr.strip() or stdout.strip()}"
        return "Typing indicator sent."

    async def send_paused(self, to: str) -> str:
        """Clear typing indicator."""
        if not to:
            return "Error: recipient is required"
        stdout, stderr, rc = await _run(
            [*self._base_args, "presence", "paused", "--to", to]
        )
        if rc != 0:
            return f"Error clearing typing: {stderr.strip() or stdout.strip()}"
        return "Typing indicator cleared."


# ---------------------------------------------------------------------------
# Formatters — parse wacli JSON output into readable text
# ---------------------------------------------------------------------------


def _parse_json_output(raw: str) -> list[dict[str, Any]]:
    """Parse wacli --json output (NDJSON or single JSON object with .data)."""
    raw = raw.strip()
    if not raw:
        return []
    # Try single JSON (wacli wraps lists in {"data": ...})
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "data" in parsed:
            data = parsed["data"]
            # data can be a list directly, or a dict with a nested list
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                # Look for the first list value (e.g. data.messages, data.chats)
                for v in data.values():
                    if isinstance(v, list):
                        return v
                return [data]
            return []
        if isinstance(parsed, list):
            return parsed
        return [parsed]
    except json.JSONDecodeError:
        pass
    # Try NDJSON
    items = []
    for line in raw.splitlines():
        line = line.strip()
        if line:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def _format_chats(raw: str) -> str:
    items = _parse_json_output(raw)
    if not items:
        return "No chats found."
    lines = []
    for chat in items:
        name = chat.get("Name") or chat.get("name") or chat.get("JID", "Unknown")
        jid = chat.get("JID") or chat.get("jid", "")
        unread = chat.get("UnreadCount") or chat.get("unread_count", 0)
        marker = f" ({unread} unread)" if unread else ""
        lines.append(f"- {name} [{jid}]{marker}")
    return "\n".join(lines)


def _format_messages(raw: str) -> str:
    items = _parse_json_output(raw)
    if not items:
        return "No messages found."
    lines = []
    for msg in items:
        sender = msg.get("SenderName") or msg.get("sender_name") or msg.get("Sender") or "?"
        text = msg.get("Text") or msg.get("text") or msg.get("Body") or ""
        ts = msg.get("Timestamp") or msg.get("timestamp") or ""
        direction = "→" if msg.get("IsFromMe") or msg.get("is_from_me") else "←"
        lines.append(f"[{ts}] {direction} {sender}: {text}")
    return "\n".join(lines) if lines else raw


def _format_contacts(raw: str) -> str:
    items = _parse_json_output(raw)
    if not items:
        return "No contacts found."
    lines = []
    for contact in items:
        name = contact.get("FullName") or contact.get("full_name") or contact.get("Name") or "?"
        phone = contact.get("Phone") or contact.get("phone") or contact.get("JID", "")
        lines.append(f"- {name} [{phone}]")
    return "\n".join(lines)


def _format_groups(raw: str) -> str:
    items = _parse_json_output(raw)
    if not items:
        return "No groups found."
    lines = []
    for group in items:
        name = group.get("Name") or group.get("name") or group.get("Subject") or "?"
        jid = group.get("JID") or group.get("jid", "")
        participants = group.get("ParticipantCount") or group.get("participant_count") or ""
        p_str = f" ({participants} members)" if participants else ""
        lines.append(f"- {name} [{jid}]{p_str}")
    return "\n".join(lines)
