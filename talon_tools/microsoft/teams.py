"""
Microsoft Teams integration — list teams, channels, and read messages via Graph.

Sync functions — wrap in run_in_executor() for async.
"""

from __future__ import annotations

import httpx

from .auth import get_token, GRAPH_BASE


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=GRAPH_BASE,
        headers={"Authorization": f"Bearer {get_token()}"},
        timeout=30,
    )


def list_teams() -> str:
    """List teams the user is a member of."""
    with _client() as c:
        r = c.get("/me/joinedTeams", params={"$select": "id,displayName,description"})
        r.raise_for_status()

    teams = r.json().get("value", [])
    if not teams:
        return "Not a member of any teams."

    lines = []
    for t in teams:
        desc = f" — {t['description']}" if t.get("description") else ""
        lines.append(f"[{t['id']}] {t.get('displayName', '(unnamed)')}{desc}")
    return "\n".join(lines)


def list_channels(team_id: str) -> str:
    """List channels in a team."""
    with _client() as c:
        r = c.get(
            f"/teams/{team_id}/channels",
            params={"$select": "id,displayName,description"},
        )
        r.raise_for_status()

    channels = r.json().get("value", [])
    if not channels:
        return "No channels found."

    lines = []
    for ch in channels:
        desc = f" — {ch['description']}" if ch.get("description") else ""
        lines.append(f"[{ch['id']}] {ch.get('displayName', '(unnamed)')}{desc}")
    return "\n".join(lines)


def list_channel_messages(team_id: str, channel_id: str, max_results: int = 15) -> str:
    """List recent messages in a team channel."""
    with _client() as c:
        r = c.get(
            f"/teams/{team_id}/channels/{channel_id}/messages",
            params={
                "$top": max_results,
                "$select": "id,createdDateTime,from,body",
            },
        )
        r.raise_for_status()

    messages = r.json().get("value", [])
    if not messages:
        return "No messages in this channel."

    return _format_messages(messages)


def list_chats(max_results: int = 15) -> str:
    """List recent 1:1 and group chats."""
    with _client() as c:
        r = c.get(
            "/me/chats",
            params={
                "$top": max_results,
                "$select": "id,topic,chatType,lastUpdatedDateTime",
                "$orderby": "lastUpdatedDateTime desc",
                "$expand": "members($select=displayName)",
            },
        )
        r.raise_for_status()

    chats = r.json().get("value", [])
    if not chats:
        return "No chats found."

    lines = []
    for ch in chats:
        topic = ch.get("topic") or ch.get("chatType", "unknown")
        members = ch.get("members", [])
        member_names = ", ".join(m.get("displayName", "") for m in members[:5])
        if member_names:
            topic = f"{topic} ({member_names})"
        lines.append(f"[{ch['id']}] {ch.get('lastUpdatedDateTime', '')} | {topic}")
    return "\n".join(lines)


def list_chat_messages(chat_id: str, max_results: int = 15) -> str:
    """List recent messages in a 1:1 or group chat."""
    with _client() as c:
        r = c.get(
            f"/me/chats/{chat_id}/messages",
            params={
                "$top": max_results,
                "$select": "id,createdDateTime,from,body",
            },
        )
        r.raise_for_status()

    messages = r.json().get("value", [])
    if not messages:
        return "No messages in this chat."

    return _format_messages(messages)


def _format_messages(messages: list[dict]) -> str:
    """Format a list of Graph chat/channel messages."""
    import re

    lines = []
    for m in messages:
        sender = (
            m.get("from", {}).get("user", {}).get("displayName", "")
            or m.get("from", {}).get("application", {}).get("displayName", "system")
        )
        body = m.get("body", {}).get("content", "")
        if m.get("body", {}).get("contentType") == "html":
            body = re.sub(r"<[^>]+>", "", body).strip()
        body = body[:300] if body else "(empty)"
        ts = m.get("createdDateTime", "")
        lines.append(f"[{ts}] {sender}: {body}")
    return "\n".join(lines)
