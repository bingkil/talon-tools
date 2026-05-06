"""
Google Docs integration — read and search documents.

Uses the Docs API for reading and Drive API for searching/listing.
Sync functions — wrap in run_in_executor() for async.
"""

from __future__ import annotations

from googleapiclient.discovery import build

from .auth import get_credentials


def _docs_service(token_file=None):
    return build("docs", "v1", credentials=get_credentials(token_file))


def _drive_service(token_file=None):
    return build("drive", "v3", credentials=get_credentials(token_file))


def _extract_text(doc: dict) -> str:
    """Extract plain text from a Google Doc's body content."""
    text_parts = []
    for element in doc.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if paragraph:
            for pe in paragraph.get("elements", []):
                text_run = pe.get("textRun")
                if text_run:
                    text_parts.append(text_run.get("content", ""))
    return "".join(text_parts)


def read_document(document_id: str, token_file=None) -> str:
    """Read the full text content of a Google Doc by ID."""
    svc = _docs_service(token_file)
    doc = svc.documents().get(documentId=document_id).execute()
    title = doc.get("title", "(untitled)")
    text = _extract_text(doc)
    return f"Title: {title}\n---\n{text}"


def search_documents(query: str, max_results: int = 10, token_file=None) -> str:
    """Search Google Docs by name/content via Drive API."""
    svc = _drive_service(token_file)
    q = f"mimeType='application/vnd.google-apps.document' and name contains '{query}'"
    result = svc.files().list(
        q=q,
        pageSize=max_results,
        fields="files(id, name, modifiedTime)",
        orderBy="modifiedTime desc",
    ).execute()

    files = result.get("files", [])
    if not files:
        return f"No documents found matching: {query}"

    lines = []
    for f in files:
        lines.append(f"[{f['id']}] {f.get('modifiedTime', '')} | {f['name']}")

    return "\n".join(lines)


def list_recent_documents(max_results: int = 10, token_file=None) -> str:
    """List recently modified Google Docs."""
    svc = _drive_service(token_file)
    result = svc.files().list(
        q="mimeType='application/vnd.google-apps.document'",
        pageSize=max_results,
        fields="files(id, name, modifiedTime)",
        orderBy="modifiedTime desc",
    ).execute()

    files = result.get("files", [])
    if not files:
        return "No documents found."

    lines = []
    for f in files:
        lines.append(f"[{f['id']}] {f.get('modifiedTime', '')} | {f['name']}")

    return "\n".join(lines)
