"""Cross-platform Chrome bookmarks reader."""

from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any


def _default_bookmarks_path(username: str = "") -> Path:
    """Resolve the Chrome Bookmarks JSON path for the current OS.

    Args:
        username: OS username. If empty, uses the current user's home directory.

    Returns:
        Path to Chrome's Bookmarks JSON file.
    """
    system = platform.system()

    if username:
        if system == "Windows":
            home = Path(f"C:/Users/{username}")
        elif system == "Darwin":
            home = Path(f"/Users/{username}")
        else:
            home = Path(f"/home/{username}")
    else:
        home = Path.home()

    if system == "Windows":
        return home / "AppData" / "Local" / "Google" / "Chrome" / "User Data" / "Default" / "Bookmarks"
    elif system == "Darwin":
        return home / "Library" / "Application Support" / "Google" / "Chrome" / "Default" / "Bookmarks"
    else:
        return home / ".config" / "google-chrome" / "Default" / "Bookmarks"


def _flatten_nodes(node: dict[str, Any], folder_path: str = "") -> list[dict[str, str]]:
    """Recursively flatten the Chrome bookmark tree into a list."""
    results = []
    node_type = node.get("type", "")
    name = node.get("name", "")
    current_path = f"{folder_path}/{name}" if folder_path else name

    if node_type == "url":
        results.append({
            "title": name,
            "url": node.get("url", ""),
            "folder": folder_path,
            "date_added": node.get("date_added", ""),
        })
    elif node_type == "folder":
        for child in node.get("children", []):
            results.extend(_flatten_nodes(child, current_path))

    return results


def read_bookmarks(
    username: str = "",
    path: str = "",
    folder: str = "",
    query: str = "",
    limit: int = 50,
) -> str:
    """Read Chrome bookmarks and return formatted output.

    Args:
        username: OS username (optional — defaults to current user).
        path: Explicit path to Bookmarks file (overrides username/platform detection).
        folder: Filter to bookmarks within this folder path (substring match).
        query: Filter bookmarks by title or URL substring (case-insensitive).
        limit: Max bookmarks to return (default 50).

    Returns:
        Formatted string of bookmarks.
    """
    bookmarks_path = Path(path) if path else _default_bookmarks_path(username)

    if not bookmarks_path.is_file():
        return f"Bookmarks file not found at: {bookmarks_path}"

    data = json.loads(bookmarks_path.read_text(encoding="utf-8"))
    roots = data.get("roots", {})

    all_bookmarks: list[dict[str, str]] = []
    for root_name, root_node in roots.items():
        if isinstance(root_node, dict) and "children" in root_node:
            all_bookmarks.extend(_flatten_nodes(root_node))

    # Apply folder filter
    if folder:
        folder_lower = folder.lower()
        all_bookmarks = [b for b in all_bookmarks if folder_lower in b["folder"].lower()]

    # Apply query filter
    if query:
        query_lower = query.lower()
        all_bookmarks = [
            b for b in all_bookmarks
            if query_lower in b["title"].lower() or query_lower in b["url"].lower()
        ]

    total = len(all_bookmarks)
    bookmarks = all_bookmarks[:limit]

    if not bookmarks:
        return "No bookmarks found matching the criteria."

    lines = [f"Found {total} bookmark(s)" + (f" (showing first {limit})" if total > limit else "") + ":\n"]
    for b in bookmarks:
        lines.append(f"- [{b['title']}]({b['url']})")
        if b["folder"]:
            lines.append(f"  Folder: {b['folder']}")

    return "\n".join(lines)
