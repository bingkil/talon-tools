"""
Gmail integration — list, read, search, send, and manage emails.

All functions are sync (Google API client is sync). Wrap in
asyncio.run_in_executor() when calling from async contexts.
"""

from __future__ import annotations

import base64
import mimetypes
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path

from googleapiclient.discovery import build

from .auth import get_credentials

def _service(token_file=None):
    return build("gmail", "v1", credentials=get_credentials(token_file))


def _extract_body(payload: dict) -> str:
    """Recursively extract plain text from a message payload."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return base64.urlsafe_b64decode(data).decode("utf-8") if data else ""
    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text
    return ""


def _headers_dict(msg: dict) -> dict[str, str]:
    return {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}


def list_inbox(max_results: int = 10, query: str = "", token_file=None) -> str:
    """List recent inbox messages. Optional query filter (Gmail search syntax)."""
    svc = _service(token_file)
    kwargs = {"userId": "me", "labelIds": ["INBOX"], "maxResults": max_results}
    if query:
        kwargs["q"] = query
    result = svc.users().messages().list(**kwargs).execute()
    messages = result.get("messages", [])

    if not messages:
        return "Inbox is empty." if not query else f"No messages matching: {query}"

    lines = []
    for msg in messages:
        detail = svc.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        h = _headers_dict(detail)
        lines.append(f"[{msg['id']}] {h.get('Date', '')} | {h.get('From', '')} | {h.get('Subject', '')}")

    return "\n".join(lines)


def read_message(message_id: str, token_file=None) -> str:
    """Read the full content of an email by ID."""
    svc = _service(token_file)
    msg = svc.users().messages().get(userId="me", id=message_id, format="full").execute()
    h = _headers_dict(msg)

    body = _extract_body(msg["payload"])
    snippet = msg.get("snippet", "")

    parts = [
        f"From: {h.get('From', '')}",
        f"To: {h.get('To', '')}",
        f"Subject: {h.get('Subject', '')}",
        f"Date: {h.get('Date', '')}",
        "---",
        body or snippet or "(no text body)",
    ]
    return "\n".join(parts)


def search_messages(query: str, max_results: int = 5, token_file=None) -> str:
    """Search emails using Gmail search syntax."""
    svc = _service(token_file)
    result = svc.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = result.get("messages", [])

    if not messages:
        return f"No messages found for: {query}"

    lines = []
    for msg in messages:
        detail = svc.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        h = _headers_dict(detail)
        lines.append(f"[{msg['id']}] {h.get('Date', '')} | {h.get('From', '')} | {h.get('Subject', '')}")

    return "\n".join(lines)


def send_email(to: str, subject: str, body: str, attachments: list[str] | None = None, token_file=None) -> str:
    """Send an email, optionally with file attachments.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body (plain text).
        attachments: Optional list of local file paths to attach.
    """
    svc = _service(token_file)

    if attachments:
        message = MIMEMultipart()
        message["to"] = to
        message["subject"] = subject
        message.attach(MIMEText(body))

        for filepath in attachments:
            path = Path(filepath)
            if not path.exists():
                return f"Error: attachment not found: {filepath}"
            mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            main_type, sub_type = mime_type.split("/", 1)
            with open(path, "rb") as f:
                part = MIMEBase(main_type, sub_type)
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=path.name)
            message.attach(part)
    else:
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    sent = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
    return f"Sent (id: {sent['id']})"


def create_draft(to: str, subject: str, body: str, attachments: list[str] | None = None, token_file=None) -> str:
    """Create a draft email, optionally with file attachments.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body (plain text).
        attachments: Optional list of local file paths to attach.
    """
    svc = _service(token_file)

    if attachments:
        message = MIMEMultipart()
        message["to"] = to
        message["subject"] = subject
        message.attach(MIMEText(body))

        for filepath in attachments:
            path = Path(filepath)
            if not path.exists():
                return f"Error: attachment not found: {filepath}"
            mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            main_type, sub_type = mime_type.split("/", 1)
            with open(path, "rb") as f:
                part = MIMEBase(main_type, sub_type)
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=path.name)
            message.attach(part)
    else:
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft = svc.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    return f"Draft created (id: {draft['id']})"


def mark_as_read(message_id: str, token_file=None) -> str:
    """Mark a message as read."""
    svc = _service(token_file)
    svc.users().messages().modify(
        userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
    ).execute()
    return f"Marked {message_id} as read"


def trash_message(message_id: str, token_file=None) -> str:
    """Move a message to trash."""
    svc = _service(token_file)
    svc.users().messages().trash(userId="me", id=message_id).execute()
    return f"Trashed {message_id}"
