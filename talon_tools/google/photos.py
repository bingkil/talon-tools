"""
Google Photos Library API — search and list photos/albums.

Sync functions — wrap in run_in_executor() for async.

Note: The Photos Library API does NOT use the standard googleapiclient discovery.
It requires direct REST calls via the authorized session.
"""

from __future__ import annotations

from google.auth.transport.requests import AuthorizedSession

from .auth import get_credentials

_sessions: dict[str, AuthorizedSession] = {}


def _session(token_file=None) -> AuthorizedSession:
    key = str(token_file) if token_file else "__default__"
    if key not in _sessions:
        _sessions[key] = AuthorizedSession(get_credentials(token_file))
    return _sessions[key]


BASE = "https://photoslibrary.googleapis.com/v1"


def search_photos(query: str, max_results: int = 10, token_file=None) -> str:
    """Search photos by content category or date filter.

    The Photos API doesn't support free-text search — it uses content categories
    and date filters.
    """
    session = _session(token_file)

    body: dict = {"pageSize": min(max_results, 100)}

    categories = {
        "animals", "arts", "birthdays", "cityscapes", "crafts", "documents",
        "fashion", "flowers", "food", "gardens", "holidays", "houses",
        "landmarks", "landscapes", "night", "people", "performances", "pets",
        "receipts", "screenshots", "selfies", "sport", "travel", "utility",
        "weddings", "whiteboards",
    }

    query_lower = query.lower().strip()
    matched = [c.upper() for c in categories if c in query_lower]

    if matched:
        body["filters"] = {
            "contentFilter": {"includedContentCategories": matched}
        }

    resp = session.post(f"{BASE}/mediaItems:search", json=body)
    resp.raise_for_status()
    data = resp.json()

    items = data.get("mediaItems", [])
    if not items:
        return f"No photos found for: {query}"

    return _format_items(items)


def list_photos(max_results: int = 10, token_file=None) -> str:
    """List recent photos."""
    session = _session(token_file)
    resp = session.get(f"{BASE}/mediaItems", params={"pageSize": min(max_results, 100)})
    resp.raise_for_status()
    data = resp.json()

    items = data.get("mediaItems", [])
    if not items:
        return "No photos found."

    return _format_items(items)


def list_albums(max_results: int = 20, token_file=None) -> str:
    """List photo albums."""
    session = _session(token_file)
    resp = session.get(f"{BASE}/albums", params={"pageSize": min(max_results, 50)})
    resp.raise_for_status()
    data = resp.json()

    albums = data.get("albums", [])
    if not albums:
        return "No albums found."

    lines = []
    for a in albums:
        count = a.get("mediaItemsCount", "?")
        lines.append(f"[{a['id']}] {a.get('title', '(untitled)')} ({count} items)")

    return "\n".join(lines)


def get_album_photos(album_id: str, max_results: int = 20, token_file=None) -> str:
    """List photos in a specific album."""
    session = _session(token_file)
    body = {"albumId": album_id, "pageSize": min(max_results, 100)}
    resp = session.post(f"{BASE}/mediaItems:search", json=body)
    resp.raise_for_status()
    data = resp.json()

    items = data.get("mediaItems", [])
    if not items:
        return "No photos in this album."

    return _format_items(items)


def _format_items(items: list[dict]) -> str:
    lines = []
    for item in items:
        meta = item.get("mediaMetadata", {})
        created = meta.get("creationTime", "")
        width = meta.get("width", "?")
        height = meta.get("height", "?")
        filename = item.get("filename", "")
        desc = item.get("description", "")
        url = item.get("productUrl", "")

        line = f"[{item['id']}] {created[:10]} {filename} ({width}x{height})"
        if desc:
            line += f" \u2014 {desc}"
        if url:
            line += f"\n  {url}"
        lines.append(line)

    return "\n".join(lines)
