"""
Google Calendar integration — list, create, and manage events.

Sync functions — wrap in run_in_executor() for async.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from googleapiclient.discovery import build

from .auth import get_credentials


def _service(token_file=None):
    return build("calendar", "v3", credentials=get_credentials(token_file))


def list_events(max_results: int = 10, days_ahead: int = 7, token_file=None) -> str:
    """List upcoming events from the primary calendar."""
    svc = _service(token_file)
    now = datetime.utcnow().isoformat() + "Z"
    end = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"

    result = svc.events().list(
        calendarId="primary",
        timeMin=now,
        timeMax=end,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])
    if not events:
        return f"No events in the next {days_ahead} days."

    lines = []
    for e in events:
        start = e["start"].get("dateTime", e["start"].get("date", ""))
        end_t = e["end"].get("dateTime", e["end"].get("date", ""))
        summary = e.get("summary", "(no title)")
        location = e.get("location", "")
        loc_str = f" @ {location}" if location else ""
        lines.append(f"[{e['id']}] {start} \u2192 {end_t} | {summary}{loc_str}")

    return "\n".join(lines)


def get_event(event_id: str, token_file=None) -> str:
    """Get full details of a calendar event."""
    svc = _service(token_file)
    e = svc.events().get(calendarId="primary", eventId=event_id).execute()

    start = e["start"].get("dateTime", e["start"].get("date", ""))
    end = e["end"].get("dateTime", e["end"].get("date", ""))
    parts = [
        f"Title: {e.get('summary', '(no title)')}",
        f"When: {start} \u2192 {end}",
    ]
    if e.get("location"):
        parts.append(f"Where: {e['location']}")
    if e.get("description"):
        parts.append(f"Description: {e['description']}")
    attendees = e.get("attendees", [])
    if attendees:
        names = [a.get("email", "") for a in attendees[:10]]
        parts.append(f"Attendees: {', '.join(names)}")
    return "\n".join(parts)


def create_event(
    summary: str,
    start: str,
    end: str,
    description: str = "",
    location: str = "",
    timezone: str = "Europe/Bratislava",
    token_file=None,
) -> str:
    """Create a calendar event. start/end: ISO datetime like '2026-05-03T14:00:00'."""
    svc = _service(token_file)
    body = {
        "summary": summary,
        "start": {"dateTime": start, "timeZone": timezone},
        "end": {"dateTime": end, "timeZone": timezone},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location

    event = svc.events().insert(calendarId="primary", body=body).execute()
    return f"Created event: {event.get('summary', '')} (id: {event['id']})"


def delete_event(event_id: str, token_file=None) -> str:
    """Delete a calendar event."""
    svc = _service(token_file)
    svc.events().delete(calendarId="primary", eventId=event_id).execute()
    return f"Deleted event {event_id}"
