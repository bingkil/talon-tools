"""
Google Drive integration — list, search, upload, download, and manage files.

Uses the Drive API v3 with drive.file and drive.readonly scopes.
Sync functions — wrap in run_in_executor() for async.
"""

from __future__ import annotations

import io
import mimetypes
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from .auth import get_credentials


def _service(token_file=None):
    return build("drive", "v3", credentials=get_credentials(token_file))


def list_files(max_results: int = 10, folder_id: str = "", token_file=None) -> str:
    """List files in Drive, optionally within a specific folder."""
    svc = _service(token_file)
    q = "trashed = false"
    if folder_id:
        q += f" and '{folder_id}' in parents"
    result = svc.files().list(
        q=q,
        pageSize=max_results,
        fields="files(id, name, mimeType, modifiedTime, size)",
        orderBy="modifiedTime desc",
    ).execute()

    files = result.get("files", [])
    if not files:
        return "No files found."

    lines = []
    for f in files:
        size = f.get("size", "")
        size_str = f" ({_human_size(int(size))})" if size else ""
        lines.append(f"[{f['id']}] {f['name']}{size_str} | {f.get('mimeType', '')} | {f.get('modifiedTime', '')}")
    return "\n".join(lines)


def search_files(query: str, max_results: int = 10, token_file=None) -> str:
    """Search Drive files by name."""
    svc = _service(token_file)
    q = f"name contains '{query}' and trashed = false"
    result = svc.files().list(
        q=q,
        pageSize=max_results,
        fields="files(id, name, mimeType, modifiedTime, size)",
        orderBy="modifiedTime desc",
    ).execute()

    files = result.get("files", [])
    if not files:
        return f"No files found matching: {query}"

    lines = []
    for f in files:
        size = f.get("size", "")
        size_str = f" ({_human_size(int(size))})" if size else ""
        lines.append(f"[{f['id']}] {f['name']}{size_str} | {f.get('mimeType', '')} | {f.get('modifiedTime', '')}")
    return "\n".join(lines)


def get_file_info(file_id: str, token_file=None) -> str:
    """Get metadata about a file by ID."""
    svc = _service(token_file)
    f = svc.files().get(
        fileId=file_id,
        fields="id, name, mimeType, modifiedTime, size, webViewLink, parents",
    ).execute()

    lines = [
        f"Name: {f['name']}",
        f"ID: {f['id']}",
        f"Type: {f.get('mimeType', '')}",
        f"Modified: {f.get('modifiedTime', '')}",
    ]
    if f.get("size"):
        lines.append(f"Size: {_human_size(int(f['size']))}")
    if f.get("webViewLink"):
        lines.append(f"Link: {f['webViewLink']}")
    if f.get("parents"):
        lines.append(f"Parent: {f['parents'][0]}")
    return "\n".join(lines)


def upload_file(local_path: str, folder_id: str = "", name: str = "", token_file=None) -> str:
    """Upload a local file to Google Drive."""
    svc = _service(token_file)
    path = Path(local_path)
    if not path.exists():
        return f"Error: file not found: {local_path}"

    file_name = name or path.name
    mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

    metadata: dict = {"name": file_name}
    if folder_id:
        metadata["parents"] = [folder_id]

    media = MediaFileUpload(str(path), mimetype=mime_type, resumable=True)
    f = svc.files().create(
        body=metadata, media_body=media, fields="id, name, webViewLink"
    ).execute()

    link = f.get("webViewLink", "")
    return f"Uploaded: {f['name']} (id: {f['id']})\nLink: {link}"


def download_file(file_id: str, local_path: str, token_file=None) -> str:
    """Download a Drive file to a local path."""
    svc = _service(token_file)

    # Get file metadata to check type
    meta = svc.files().get(fileId=file_id, fields="name, mimeType").execute()
    mime = meta.get("mimeType", "")

    dest = Path(local_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Google Workspace files need export
    export_map = {
        "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
        "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
        "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
    }

    if mime in export_map:
        export_mime, ext = export_map[mime]
        if not dest.suffix:
            dest = dest.with_suffix(ext)
        request = svc.files().export_media(fileId=file_id, mimeType=export_mime)
    else:
        request = svc.files().get_media(fileId=file_id)

    fh = io.FileIO(str(dest), "wb")
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.close()

    return f"Downloaded: {meta['name']} -> {dest}"


def create_folder(name: str, parent_id: str = "", token_file=None) -> str:
    """Create a folder in Google Drive."""
    svc = _service(token_file)
    metadata: dict = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    f = svc.files().create(body=metadata, fields="id, name, webViewLink").execute()
    link = f.get("webViewLink", "")
    return f"Created folder: {f['name']} (id: {f['id']})\nLink: {link}"


def move_file(file_id: str, new_parent_id: str, token_file=None) -> str:
    """Move a file to a different folder."""
    svc = _service(token_file)
    # Get current parents
    f = svc.files().get(fileId=file_id, fields="parents, name").execute()
    old_parents = ",".join(f.get("parents", []))

    svc.files().update(
        fileId=file_id,
        addParents=new_parent_id,
        removeParents=old_parents,
        fields="id, name, parents",
    ).execute()

    return f"Moved '{f['name']}' to folder {new_parent_id}"


def delete_file(file_id: str, token_file=None) -> str:
    """Move a file to trash."""
    svc = _service(token_file)
    svc.files().update(fileId=file_id, body={"trashed": True}).execute()
    return f"Trashed file {file_id}"


def _human_size(size_bytes: int) -> str:
    """Format bytes to human-readable size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}" if unit == "B" else f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
