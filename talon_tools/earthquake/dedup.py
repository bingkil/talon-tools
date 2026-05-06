"""
Deduplication for earthquake event monitoring.

Stores seen event IDs in a JSON file on disk so events are never
reported more than once across heartbeats.
"""

from __future__ import annotations

import json
from pathlib import Path


_DEFAULT_MAX_SEEN = 500  # cap stored IDs so the file doesn't grow forever


def load_seen(state_file: Path) -> set[str]:
    """Load seen event IDs from disk. Returns empty set if file doesn't exist."""
    if not state_file.exists():
        return set()
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        return set(data.get("seen_ids", []))
    except Exception:
        return set()


def save_seen(state_file: Path, seen: set[str], max_ids: int = _DEFAULT_MAX_SEEN) -> None:
    """Persist seen event IDs to disk. Trims to max_ids most-recently-added entries."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    # Convert to list; trim if over cap (just keep last max_ids)
    ids_list = list(seen)[-max_ids:]
    state_file.write_text(
        json.dumps({"seen_ids": ids_list}, indent=2),
        encoding="utf-8",
    )


def filter_new(events: list[dict], seen: set[str]) -> tuple[list[dict], set[str]]:
    """
    Split events into new (unseen) and already-seen.

    Returns:
        new_events  — events not in seen set
        updated_seen — seen set updated with all event IDs from this batch
    """
    new_events = []
    updated = set(seen)
    for event in events:
        eid = event.get("id")
        if eid and eid not in seen:
            new_events.append(event)
            updated.add(eid)
    return new_events, updated
