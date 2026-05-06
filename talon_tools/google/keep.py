"""
Google Keep integration via unofficial gkeepapi.

Requires GOOGLE_KEEP_EMAIL and GOOGLE_KEEP_MASTER_TOKEN env vars.
See https://github.com/kiwiz/gkeepapi for master token setup.

State file path configurable via GOOGLE_KEEP_STATE_FILE env var.
Defaults to ~/.config/talon-google/keep_state.json.

Sync functions — wrap in run_in_executor() for async.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import gkeepapi
from talon_tools.credentials import get as cred

log = logging.getLogger(__name__)

_DEFAULT_DIR = Path.home() / ".config" / "talon-google"
STATE_FILE = Path(cred("GOOGLE_KEEP_STATE_FILE", str(_DEFAULT_DIR / "keep_state.json")))

_keep: gkeepapi.Keep | None = None


def _get_keep() -> gkeepapi.Keep:
    """Get an authenticated Keep instance, reusing across calls."""
    global _keep
    if _keep is not None:
        _keep.sync()
        return _keep

    email = cred("GOOGLE_KEEP_EMAIL", "")
    token = cred("GOOGLE_KEEP_MASTER_TOKEN", "")
    if not email or not token:
        raise RuntimeError(
            "Set GOOGLE_KEEP_EMAIL and GOOGLE_KEEP_MASTER_TOKEN env vars. "
            "See https://github.com/kiwiz/gkeepapi#obtaining-a-master-token"
        )

    keep = gkeepapi.Keep()

    state = None
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())

    keep.authenticate(email, token, state=state)

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(keep.dump()))
    _keep = keep
    return _keep


def _save_state():
    """Persist keep state to disk."""
    if _keep is not None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(_keep.dump()))


def _format_note(note) -> str:
    """Format a single note for display."""
    kind = "list" if isinstance(note, gkeepapi.node.List) else "note"
    pinned = "\U0001f4cc " if note.pinned else ""
    archived = " [archived]" if note.archived else ""
    labels = ", ".join(l.name for l in note.labels.all())
    label_str = f" #{labels}" if labels else ""

    parts = [f"{pinned}[{kind}] {note.title or '(no title)'}{archived}{label_str}"]
    parts.append(f"  id: {note.id}")

    if isinstance(note, gkeepapi.node.List):
        for item in note.items:
            check = "\u2705" if item.checked else "\u2b1c"
            parts.append(f"  {check} {item.text}")
    else:
        if note.text:
            text = note.text[:200]
            if len(note.text) > 200:
                text += "\u2026"
            parts.append(f"  {text}")

    return "\n".join(parts)


def list_notes(max_results: int = 10, pinned_only: bool = False, include_archived: bool = False) -> str:
    """List recent Keep notes."""
    keep = _get_keep()
    notes = list(keep.find(
        pinned=True if pinned_only else None,
        archived=None if include_archived else False,
        trashed=False,
    ))

    if not notes:
        return "No notes found."

    notes = notes[:max_results]
    return "\n\n".join(_format_note(n) for n in notes)


def search_notes(query: str, max_results: int = 10) -> str:
    """Search Keep notes by text content."""
    keep = _get_keep()
    notes = list(keep.find(query=query, trashed=False))

    if not notes:
        return f"No notes matching '{query}'."

    notes = notes[:max_results]
    return "\n\n".join(_format_note(n) for n in notes)


def get_note(note_id: str) -> str:
    """Get a specific note by ID."""
    keep = _get_keep()
    note = keep.get(note_id)
    if note is None:
        return f"Note {note_id} not found."
    return _format_note(note)


def create_note(title: str, text: str = "", pinned: bool = False) -> str:
    """Create a new text note."""
    keep = _get_keep()
    note = keep.createNote(title, text)
    if pinned:
        note.pinned = True
    keep.sync()
    _save_state()
    return f"Created note: {note.title} (id: {note.id})"


def create_list(title: str, items: list[str] | None = None, pinned: bool = False) -> str:
    """Create a new checklist note."""
    keep = _get_keep()
    note = keep.createList(title, [(item, False) for item in (items or [])])
    if pinned:
        note.pinned = True
    keep.sync()
    _save_state()
    return f"Created list: {note.title} with {len(items or [])} items (id: {note.id})"


def update_note(
    note_id: str,
    title: str | None = None,
    text: str | None = None,
    pinned: bool | None = None,
    archived: bool | None = None,
) -> str:
    """Update an existing note."""
    keep = _get_keep()
    note = keep.get(note_id)
    if note is None:
        return f"Note {note_id} not found."

    if title is not None:
        note.title = title
    if text is not None:
        note.text = text
    if pinned is not None:
        note.pinned = pinned
    if archived is not None:
        note.archived = archived

    keep.sync()
    _save_state()
    return f"Updated note: {note.title}"


def delete_note(note_id: str) -> str:
    """Delete (trash) a note."""
    keep = _get_keep()
    note = keep.get(note_id)
    if note is None:
        return f"Note {note_id} not found."

    title = note.title
    note.trash()
    keep.sync()
    _save_state()
    return f"Trashed note: {title}"
