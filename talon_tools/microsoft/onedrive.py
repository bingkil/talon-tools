"""
OneDrive integration — list, search, and read files via Microsoft Graph.

All functions are sync (httpx). Wrap in asyncio.run_in_executor() for async.
"""

from __future__ import annotations

import httpx

from .auth import get_token, GRAPH_BASE


def _client() -> httpx.Client:
    """Create an authenticated httpx client."""
    return httpx.Client(
        base_url=GRAPH_BASE,
        headers={"Authorization": f"Bearer {get_token('onedrive')}"},
        timeout=30,
    )


def _format_item(item: dict) -> str:
    """Format a drive item as a single line."""
    name = item.get("name", "?")
    is_folder = "folder" in item
    size = item.get("size", 0)
    modified = item.get("lastModifiedDateTime", "")[:16]
    item_id = item.get("id", "")

    if is_folder:
        child_count = item.get("folder", {}).get("childCount", 0)
        return f"[{item_id}] 📁 {name}/ ({child_count} items, modified {modified})"
    else:
        size_str = _human_size(size)
        return f"[{item_id}] {name} ({size_str}, modified {modified})"


def _human_size(nbytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.0f} {unit}" if unit == "B" else f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def list_files(path: str = "", max_results: int = 25) -> str:
    """List files and folders at a path. Empty path = root."""
    with _client() as c:
        if path and path != "/":
            path = path.strip("/")
            endpoint = f"/me/drive/root:/{path}:/children"
        else:
            endpoint = "/me/drive/root/children"

        r = c.get(endpoint, params={"$top": max_results})
        r.raise_for_status()

    items = r.json().get("value", [])
    if not items:
        return f"No files found at: /{path}" if path else "OneDrive root is empty."

    lines = [_format_item(item) for item in items]
    return "\n".join(lines)


def search_files(query: str, max_results: int = 15) -> str:
    """Search OneDrive files by name or content."""
    with _client() as c:
        r = c.get(
            f"/me/drive/root/search(q='{query}')",
            params={"$top": max_results, "$select": "id,name,size,lastModifiedDateTime,folder,parentReference"},
        )
        r.raise_for_status()

    items = r.json().get("value", [])
    if not items:
        return f"No files found for: {query}"

    lines = []
    for item in items:
        parent = item.get("parentReference", {}).get("path", "")
        # Strip the /drive/root: prefix
        parent = parent.replace("/drive/root:", "") or "/"
        line = _format_item(item)
        lines.append(f"{line}  in {parent}")
    return "\n".join(lines)


def read_file(item_id: str) -> str:
    """Read the text content of a file by its item ID. Works for text, CSV, markdown, etc."""
    with _client() as c:
        # Get metadata first to check size/type
        meta_r = c.get(f"/me/drive/items/{item_id}", params={"$select": "name,size,file"})
        meta_r.raise_for_status()
        meta = meta_r.json()

        name = meta.get("name", "unknown")
        size = meta.get("size", 0)
        mime = meta.get("file", {}).get("mimeType", "")

        # Guard against huge files
        if size > 512_000:  # 500KB
            return f"File '{name}' is too large to read inline ({_human_size(size)}). Download it instead."

        # Guard against binary
        binary_prefixes = ("image/", "video/", "audio/", "application/zip", "application/x-", "application/octet")
        if any(mime.startswith(p) for p in binary_prefixes):
            return f"File '{name}' is binary ({mime}). Cannot display inline."

        # Download content
        r = c.get(f"/me/drive/items/{item_id}/content", follow_redirects=True)
        r.raise_for_status()

        try:
            text = r.text
        except Exception:
            return f"File '{name}' could not be decoded as text."

        return f"--- {name} ---\n{text}"


def get_info(item_id: str) -> str:
    """Get detailed metadata for a file or folder."""
    with _client() as c:
        r = c.get(f"/me/drive/items/{item_id}")
        r.raise_for_status()

    item = r.json()
    name = item.get("name", "?")
    is_folder = "folder" in item
    size = _human_size(item.get("size", 0))
    created = item.get("createdDateTime", "")[:16]
    modified = item.get("lastModifiedDateTime", "")[:16]
    created_by = item.get("createdBy", {}).get("user", {}).get("displayName", "?")
    modified_by = item.get("lastModifiedBy", {}).get("user", {}).get("displayName", "?")
    web_url = item.get("webUrl", "")
    parent_path = item.get("parentReference", {}).get("path", "").replace("/drive/root:", "") or "/"

    lines = [
        f"Name: {name}",
        f"Type: {'Folder' if is_folder else 'File'}",
        f"Size: {size}",
        f"Location: {parent_path}",
        f"Created: {created} by {created_by}",
        f"Modified: {modified} by {modified_by}",
        f"URL: {web_url}",
    ]

    if is_folder:
        lines.append(f"Items: {item.get('folder', {}).get('childCount', 0)}")

    if not is_folder:
        mime = item.get("file", {}).get("mimeType", "unknown")
        lines.append(f"MIME: {mime}")

    return "\n".join(lines)
