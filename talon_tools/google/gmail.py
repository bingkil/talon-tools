"""
Gmail integration — list, read, search, send, and manage emails.

All functions are sync (Google API client is sync). Wrap in
asyncio.run_in_executor() when calling from async contexts.
"""

from __future__ import annotations

import base64
import email.utils
import mimetypes
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path
from typing import Any

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


def _extract_attachments(payload: dict) -> list[dict]:
    """Recursively extract attachment metadata from a message payload."""
    attachments = []
    for part in payload.get("parts", []):
        filename = part.get("filename", "")
        body = part.get("body", {})
        attachment_id = body.get("attachmentId")
        if attachment_id and filename:
            attachments.append({
                "filename": filename,
                "mime_type": part.get("mimeType", ""),
                "attachment_id": attachment_id,
                "size": body.get("size", 0),
            })
        if part.get("parts"):
            attachments.extend(_extract_attachments(part))
    return attachments


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
    """Read the full content of an email by ID, including attachment metadata."""
    svc = _service(token_file)
    msg = svc.users().messages().get(userId="me", id=message_id, format="full").execute()
    h = _headers_dict(msg)

    body = _extract_body(msg["payload"])
    snippet = msg.get("snippet", "")
    attachments = _extract_attachments(msg["payload"])

    parts = [
        f"From: {h.get('From', '')}",
        f"To: {h.get('To', '')}",
        f"Subject: {h.get('Subject', '')}",
        f"Date: {h.get('Date', '')}",
        f"Thread: {msg.get('threadId', '')}",
        "---",
        body or snippet or "(no text body)",
    ]

    if attachments:
        parts.append("\n--- Attachments ---")
        for att in attachments:
            size_kb = att["size"] // 1024
            parts.append(
                f"  {att['filename']} ({att['mime_type']}, {size_kb}KB)"
                f"  attachment_id: {att['attachment_id']}"
            )

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


def mark_as_unread(message_id: str, token_file=None) -> str:
    """Mark a message as unread."""
    svc = _service(token_file)
    svc.users().messages().modify(
        userId="me", id=message_id, body={"addLabelIds": ["UNREAD"]}
    ).execute()
    return f"Marked {message_id} as unread"


def archive_message(message_id: str, token_file=None) -> str:
    """Archive a message (remove from inbox without deleting)."""
    svc = _service(token_file)
    svc.users().messages().modify(
        userId="me", id=message_id, body={"removeLabelIds": ["INBOX"]}
    ).execute()
    return f"Archived {message_id}"


def star_message(message_id: str, token_file=None) -> str:
    """Add a star to a message."""
    svc = _service(token_file)
    svc.users().messages().modify(
        userId="me", id=message_id, body={"addLabelIds": ["STARRED"]}
    ).execute()
    return f"Starred {message_id}"


def unstar_message(message_id: str, token_file=None) -> str:
    """Remove star from a message."""
    svc = _service(token_file)
    svc.users().messages().modify(
        userId="me", id=message_id, body={"removeLabelIds": ["STARRED"]}
    ).execute()
    return f"Unstarred {message_id}"


def download_attachment(
    message_id: str, attachment_id: str, filename: str, save_dir: str | None = None,
    token_file=None,
) -> str:
    """Download an email attachment to inputs/YYYY-MM-DD/HHMMSS_filename.

    Follows the same convention as channel attachments so that all incoming
    files land in the ``inputs/`` tree and are cleaned up by ``cleanup_inputs()``.

    Args:
        message_id: Gmail message ID containing the attachment.
        attachment_id: Attachment ID from gmail_read output.
        filename: Original filename for saving.
        save_dir: Override directory (default: inputs/YYYY-MM-DD/).
    """
    import re as _re
    from datetime import datetime as _dt

    svc = _service(token_file)
    att = svc.users().messages().attachments().get(
        userId="me", messageId=message_id, id=attachment_id
    ).execute()

    data = base64.urlsafe_b64decode(att["data"])

    now = _dt.now()
    if save_dir:
        out_dir = Path(save_dir)
    else:
        out_dir = Path("inputs") / now.strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _re.sub(r'[<>:"|?*]', '_', filename)
    out_name = f"{now.strftime('%H%M%S')}_{safe_name}"
    out_path = out_dir / out_name
    out_path.write_bytes(data)
    return f"Saved {filename} ({len(data)} bytes) to {out_path}"


def get_thread(thread_id: str, token_file=None) -> str:
    """Read all messages in a conversation thread."""
    svc = _service(token_file)
    thread = svc.users().threads().get(userId="me", id=thread_id, format="full").execute()
    messages = thread.get("messages", [])

    if not messages:
        return f"Thread {thread_id} is empty."

    parts = [f"Thread {thread_id} — {len(messages)} message(s)\n"]

    for i, msg in enumerate(messages, 1):
        h = _headers_dict(msg)
        body = _extract_body(msg["payload"])
        snippet = msg.get("snippet", "")
        parts.append(f"--- Message {i} [{msg['id']}] ---")
        parts.append(f"From: {h.get('From', '')}")
        parts.append(f"To: {h.get('To', '')}")
        parts.append(f"Date: {h.get('Date', '')}")
        parts.append(body or snippet or "(no text body)")
        parts.append("")

    return "\n".join(parts)


def reply_to_message(
    message_id: str, body: str, reply_all: bool = False, token_file=None,
) -> str:
    """Reply to an existing email, preserving the thread.

    Args:
        message_id: Gmail message ID to reply to.
        body: Reply body text.
        reply_all: If True, reply to all recipients (CC included).
    """
    svc = _service(token_file)
    original = svc.users().messages().get(userId="me", id=message_id, format="full").execute()
    h = _headers_dict(original)
    thread_id = original.get("threadId", "")

    # Build reply-to address
    reply_to = h.get("Reply-To") or h.get("From", "")
    subject = h.get("Subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    # Threading headers
    message_id_header = h.get("Message-ID", h.get("Message-Id", ""))
    references = h.get("References", "")
    if message_id_header:
        references = f"{references} {message_id_header}".strip()

    message = MIMEText(body)
    message["to"] = reply_to
    message["subject"] = subject
    if message_id_header:
        message["In-Reply-To"] = message_id_header
    if references:
        message["References"] = references

    # Reply-all: add original To and Cc (excluding self)
    if reply_all:
        # Get the user's own email to exclude from CC
        profile = svc.users().getProfile(userId="me").execute()
        my_email = profile.get("emailAddress", "").lower()

        all_recipients = set()
        for field in ("To", "Cc"):
            raw = h.get(field, "")
            if raw:
                for addr in raw.split(","):
                    _, email_addr = email.utils.parseaddr(addr.strip())
                    if email_addr and email_addr.lower() != my_email:
                        all_recipients.add(addr.strip())
        # Remove the reply-to address (already in To)
        _, reply_email = email.utils.parseaddr(reply_to)
        cc_list = [
            a for a in all_recipients
            if email.utils.parseaddr(a)[1].lower() != reply_email.lower()
        ]
        if cc_list:
            message["cc"] = ", ".join(cc_list)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    sent = svc.users().messages().send(
        userId="me", body={"raw": raw, "threadId": thread_id}
    ).execute()
    return f"Reply sent (id: {sent['id']}, thread: {thread_id})"


def forward_message(
    message_id: str, to: str, body: str = "", token_file=None,
) -> str:
    """Forward an email to another address.

    Args:
        message_id: Gmail message ID to forward.
        to: Recipient email address.
        body: Optional additional text to include above the forwarded message.
    """
    svc = _service(token_file)
    original = svc.users().messages().get(userId="me", id=message_id, format="full").execute()
    h = _headers_dict(original)

    original_body = _extract_body(original["payload"])
    subject = h.get("Subject", "")
    if not subject.lower().startswith("fwd:"):
        subject = f"Fwd: {subject}"

    forwarded = (
        f"---------- Forwarded message ----------\n"
        f"From: {h.get('From', '')}\n"
        f"Date: {h.get('Date', '')}\n"
        f"Subject: {h.get('Subject', '')}\n"
        f"To: {h.get('To', '')}\n\n"
        f"{original_body}"
    )

    full_body = f"{body}\n\n{forwarded}" if body else forwarded

    message = MIMEText(full_body)
    message["to"] = to
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    sent = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
    return f"Forwarded to {to} (id: {sent['id']})"


def list_labels(token_file=None) -> str:
    """List all Gmail labels (system and user-created)."""
    svc = _service(token_file)
    result = svc.users().labels().list(userId="me").execute()
    labels = result.get("labels", [])

    system = []
    user = []
    for label in sorted(labels, key=lambda l: l.get("name", "")):
        name = label["name"]
        lid = label["id"]
        if label.get("type") == "system":
            system.append(f"  {name} (id: {lid})")
        else:
            user.append(f"  {name} (id: {lid})")

    parts = ["System labels:"] + (system or ["  (none)"])
    parts += ["\nUser labels:"] + (user or ["  (none)"])
    return "\n".join(parts)


def add_label(message_id: str, label_id: str, token_file=None) -> str:
    """Add a label to a message."""
    svc = _service(token_file)
    svc.users().messages().modify(
        userId="me", id=message_id, body={"addLabelIds": [label_id]}
    ).execute()
    return f"Added label {label_id} to {message_id}"


def remove_label(message_id: str, label_id: str, token_file=None) -> str:
    """Remove a label from a message."""
    svc = _service(token_file)
    svc.users().messages().modify(
        userId="me", id=message_id, body={"removeLabelIds": [label_id]}
    ).execute()
    return f"Removed label {label_id} from {message_id}"


def create_filter(
    from_addr: str = "",
    to_addr: str = "",
    subject: str = "",
    has_words: str = "",
    exclude_words: str = "",
    has_attachment: bool | None = None,
    add_label_ids: list[str] | None = None,
    remove_label_ids: list[str] | None = None,
    forward: str = "",
    token_file=None,
) -> str:
    """Create a Gmail filter to automatically process future emails.

    Args:
        from_addr: Match emails from this sender.
        to_addr: Match emails sent to this address.
        subject: Match emails with this subject.
        has_words: Match emails containing these words.
        exclude_words: Exclude emails containing these words.
        has_attachment: If True, match only emails with attachments.
        add_label_ids: Label IDs to apply to matching emails.
        remove_label_ids: Label IDs to remove (e.g. ["INBOX"] to auto-archive).
        forward: Email address to forward matching emails to.
    """
    svc = _service(token_file)

    criteria: dict[str, Any] = {}
    if from_addr:
        criteria["from"] = from_addr
    if to_addr:
        criteria["to"] = to_addr
    if subject:
        criteria["subject"] = subject
    if has_words:
        criteria["query"] = has_words
    if exclude_words:
        criteria["negatedQuery"] = exclude_words
    if has_attachment is not None:
        criteria["hasAttachment"] = has_attachment

    if not criteria:
        return "Error: at least one filter criterion is required"

    action: dict[str, Any] = {}
    if add_label_ids:
        action["addLabelIds"] = add_label_ids
    if remove_label_ids:
        action["removeLabelIds"] = remove_label_ids
    if forward:
        action["forward"] = forward

    if not action:
        return "Error: at least one action is required (add_label_ids, remove_label_ids, or forward)"

    body = {"criteria": criteria, "action": action}
    result = svc.users().settings().filters().create(userId="me", body=body).execute()
    return f"Filter created (id: {result['id']})"
