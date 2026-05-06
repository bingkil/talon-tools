"""
Outlook Calendar integration — list events via Microsoft Graph.

Sync functions — wrap in run_in_executor() for async.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from .auth import get_token, GRAPH_BASE


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=GRAPH_BASE,
        headers={"Authorization": f"Bearer {get_token()}"},
        timeout=30,
    )


def list_events(max_results: int = 10, days_ahead: int = 7) -> str:
    """List upcoming calendar events."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days_ahead)

    with _client() as c:
        r = c.get(
            "/me/calendarView",
            params={
                "startDateTime": now.isoformat(),
                "endDateTime": end.isoformat(),
                "$top": max_results,
                "$select": "id,subject,start,end,location,organizer,attendees,isAllDay",
                "$orderby": "start/dateTime",
            },
            headers={**c.headers, "Prefer": 'outlook.timezone="UTC"'},
        )
        r.raise_for_status()

    events = r.json().get("value", [])
    if not events:
        return f"No events in the next {days_ahead} days."

    lines = []
    for e in events:
        start = e.get("start", {}).get("dateTime", "")
        end_t = e.get("end", {}).get("dateTime", "")
        subject = e.get("subject", "(no title)")
        location = e.get("location", {}).get("displayName", "")
        loc_str = f" @ {location}" if location else ""
        lines.append(f"[{e['id']}] {start} → {end_t} | {subject}{loc_str}")

    return "\n".join(lines)


def get_event(event_id: str) -> str:
    """Get full details of a calendar event."""
    with _client() as c:
        r = c.get(
            f"/me/events/{event_id}",
            params={"$select": "subject,start,end,location,body,organizer,attendees,isAllDay"},
        )
        r.raise_for_status()

    e = r.json()
    start = e.get("start", {}).get("dateTime", "")
    end = e.get("end", {}).get("dateTime", "")
    parts = [
        f"Title: {e.get('subject', '(no title)')}",
        f"When: {start} → {end}",
    ]
    loc = e.get("location", {}).get("displayName", "")
    if loc:
        parts.append(f"Where: {loc}")
    body = e.get("body", {}).get("content", "")
    if body:
        import re
        body = re.sub(r"<[^>]+>", "", body).strip()
        if body:
            parts.append(f"Description: {body[:500]}")
    organizer = e.get("organizer", {}).get("emailAddress", {})
    if organizer:
        parts.append(f"Organizer: {organizer.get('name', '')} <{organizer.get('address', '')}>")
    attendees = e.get("attendees", [])
    if attendees:
        names = [
            a.get("emailAddress", {}).get("address", "")
            for a in attendees[:15]
        ]
        parts.append(f"Attendees: {', '.join(names)}")
    return "\n".join(parts)
