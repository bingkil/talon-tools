"""
Outlook Mail integration — list, read, and search emails via Microsoft Graph.

All functions are sync (httpx). Wrap in asyncio.run_in_executor() for async.
"""

from __future__ import annotations

from functools import lru_cache

import httpx

from .auth import get_token, GRAPH_BASE


def _client() -> httpx.Client:
    """Create an authenticated httpx client."""
    return httpx.Client(
        base_url=GRAPH_BASE,
        headers={"Authorization": f"Bearer {get_token()}"},
        timeout=30,
    )


def list_inbox(max_results: int = 10, filter: str = "") -> str:
    """List recent inbox messages. Optional OData filter."""
    with _client() as c:
        params = {
            "$top": max_results,
            "$select": "id,subject,from,receivedDateTime,isRead",
            "$orderby": "receivedDateTime desc",
        }
        if filter:
            params["$filter"] = filter
        r = c.get("/me/mailFolders/inbox/messages", params=params)
        r.raise_for_status()

    messages = r.json().get("value", [])
    if not messages:
        return "Inbox is empty."

    lines = []
    for m in messages:
        from_addr = m.get("from", {}).get("emailAddress", {})
        sender = from_addr.get("name", from_addr.get("address", "unknown"))
        read_flag = "" if m.get("isRead") else " [UNREAD]"
        lines.append(
            f"[{m['id']}] {m.get('receivedDateTime', '')}"
            f" | {sender} | {m.get('subject', '(no subject)')}{read_flag}"
        )
    return "\n".join(lines)


def read_message(message_id: str) -> str:
    """Read the full content of an email by ID."""
    with _client() as c:
        r = c.get(
            f"/me/messages/{message_id}",
            params={"$select": "subject,from,toRecipients,receivedDateTime,body"},
        )
        r.raise_for_status()

    m = r.json()
    from_addr = m.get("from", {}).get("emailAddress", {})
    to_list = [
        t.get("emailAddress", {}).get("address", "")
        for t in m.get("toRecipients", [])
    ]
    body = m.get("body", {})
    # Prefer plain text; fall back to stripping HTML roughly
    content = body.get("content", "")
    if body.get("contentType") == "html":
        # Basic HTML strip — good enough for LLM consumption
        import re
        content = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.DOTALL)
        content = re.sub(r"<[^>]+>", "", content)
        content = re.sub(r"\s+", " ", content).strip()

    parts = [
        f"From: {from_addr.get('name', '')} <{from_addr.get('address', '')}>",
        f"To: {', '.join(to_list)}",
        f"Subject: {m.get('subject', '')}",
        f"Date: {m.get('receivedDateTime', '')}",
        "---",
        content or "(no body)",
    ]
    return "\n".join(parts)


def search_messages(query: str, max_results: int = 10) -> str:
    """Search emails using Microsoft Graph $search syntax."""
    with _client() as c:
        r = c.get(
            "/me/messages",
            params={
                "$search": f'"{query}"',
                "$top": max_results,
                "$select": "id,subject,from,receivedDateTime",
                "$orderby": "receivedDateTime desc",
            },
            headers={
                **c.headers,
                "ConsistencyLevel": "eventual",
            },
        )
        r.raise_for_status()

    messages = r.json().get("value", [])
    if not messages:
        return f"No messages found for: {query}"

    lines = []
    for m in messages:
        from_addr = m.get("from", {}).get("emailAddress", {})
        sender = from_addr.get("name", from_addr.get("address", "unknown"))
        lines.append(
            f"[{m['id']}] {m.get('receivedDateTime', '')}"
            f" | {sender} | {m.get('subject', '(no subject)')}"
        )
    return "\n".join(lines)
