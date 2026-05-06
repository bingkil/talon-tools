"""
Google tool definitions for LLM agents.

Provides Tool objects for Gmail, Calendar, Docs, Contacts, Photos, Tasks,
and Keep. Each tool wraps a sync Google API call and runs it in a thread pool.

Usage:
    from talon_tools.google.tools import build_tools
    tools = build_tools()                          # all Google tools (default account)
    tools = build_tools(token_file="path/to.json") # specific account
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

from talon_tools import Tool, ToolResult
from . import gmail, calendar, docs, contacts, photos, tasks, keep, sheets, drive, youtube


async def _run(fn, **kwargs):
    """Run a sync function in a thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(fn, **kwargs))


def _tool(name: str, description: str, parameters: dict, fn) -> Tool:
    """Create a Tool wrapping a sync Google API function.

    LLM-provided args are passed directly as kwargs to the function.
    Parameter names in the JSON schema must match the function signature.
    """
    async def handler(args: dict[str, Any]) -> ToolResult:
        result = await _run(fn, **args)
        return ToolResult(content=result)
    return Tool(name=name, description=description, parameters=parameters, handler=handler)


def _bind(fn, token_file):
    """Bind token_file to a function if provided."""
    return partial(fn, token_file=token_file) if token_file else fn


# ---------------------------------------------------------------------------
# Gmail
# ---------------------------------------------------------------------------

def gmail_tools(token_file=None) -> list[Tool]:
    b = partial(_bind, token_file=token_file)
    return [
        _tool("gmail_inbox",
              "List recent emails in the inbox. Optionally filter with Gmail search query.",
              {"type": "object", "properties": {
                  "max_results": {"type": "integer", "description": "Number of emails to list (default 10)"},
                  "query": {"type": "string", "description": "Gmail search query (e.g. 'from:boss@co.com is:unread')"},
              }},
              b(gmail.list_inbox)),

        _tool("gmail_read",
              "Read the full content of an email by its message ID.",
              {"type": "object", "properties": {
                  "message_id": {"type": "string", "description": "Gmail message ID"},
              }, "required": ["message_id"]},
              b(gmail.read_message)),

        _tool("gmail_search",
              "Search emails using Gmail search syntax (e.g. 'subject:invoice after:2026/04/01').",
              {"type": "object", "properties": {
                  "query": {"type": "string", "description": "Gmail search query"},
                  "max_results": {"type": "integer", "description": "Max results (default 5)"},
              }, "required": ["query"]},
              b(gmail.search_messages)),

        _tool("gmail_send",
              "Send an email with optional file attachments.",
              {"type": "object", "properties": {
                  "to": {"type": "string", "description": "Recipient email address"},
                  "subject": {"type": "string", "description": "Email subject"},
                  "body": {"type": "string", "description": "Email body (plain text)"},
                  "attachments": {"type": "array", "items": {"type": "string"}, "description": "List of local file paths to attach (optional)"},
              }, "required": ["to", "subject", "body"]},
              b(gmail.send_email)),

        _tool("gmail_draft",
              "Create a draft email with optional file attachments. Use this when the user wants to compose an email without sending it immediately.",
              {"type": "object", "properties": {
                  "to": {"type": "string", "description": "Recipient email address"},
                  "subject": {"type": "string", "description": "Email subject"},
                  "body": {"type": "string", "description": "Email body (plain text)"},
                  "attachments": {"type": "array", "items": {"type": "string"}, "description": "List of local file paths to attach (optional)"},
              }, "required": ["to", "subject", "body"]},
              b(gmail.create_draft)),
    ]


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

def calendar_tools(token_file=None) -> list[Tool]:
    b = partial(_bind, token_file=token_file)
    return [
        _tool("calendar_list",
              "List upcoming calendar events from the primary Google Calendar.",
              {"type": "object", "properties": {
                  "max_results": {"type": "integer", "description": "Max events to return (default 10)"},
                  "days_ahead": {"type": "integer", "description": "Look ahead N days (default 7)"},
              }},
              b(calendar.list_events)),

        _tool("calendar_get",
              "Get full details of a calendar event by ID.",
              {"type": "object", "properties": {
                  "event_id": {"type": "string", "description": "Calendar event ID"},
              }, "required": ["event_id"]},
              b(calendar.get_event)),

        _tool("calendar_create",
              "Create a new event on the Google Calendar.",
              {"type": "object", "properties": {
                  "summary": {"type": "string", "description": "Event title"},
                  "start": {"type": "string", "description": "Start time ISO format (e.g. 2026-05-03T14:00:00)"},
                  "end": {"type": "string", "description": "End time ISO format (e.g. 2026-05-03T15:00:00)"},
                  "description": {"type": "string", "description": "Event description (optional)"},
                  "location": {"type": "string", "description": "Event location (optional)"},
              }, "required": ["summary", "start", "end"]},
              b(calendar.create_event)),
    ]


# ---------------------------------------------------------------------------
# Docs
# ---------------------------------------------------------------------------

def docs_tools(token_file=None) -> list[Tool]:
    b = partial(_bind, token_file=token_file)
    return [
        _tool("docs_read",
              "Read the full text content of a Google Doc by its document ID.",
              {"type": "object", "properties": {
                  "document_id": {"type": "string", "description": "Google Docs document ID"},
              }, "required": ["document_id"]},
              b(docs.read_document)),

        _tool("docs_search",
              "Search Google Docs by name.",
              {"type": "object", "properties": {
                  "query": {"type": "string", "description": "Search term to find in document names"},
                  "max_results": {"type": "integer", "description": "Max results (default 10)"},
              }, "required": ["query"]},
              b(docs.search_documents)),

        _tool("docs_list",
              "List recently modified Google Docs.",
              {"type": "object", "properties": {
                  "max_results": {"type": "integer", "description": "Max results (default 10)"},
              }},
              b(docs.list_recent_documents)),
    ]


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

def contacts_tools(token_file=None) -> list[Tool]:
    b = partial(_bind, token_file=token_file)
    return [
        _tool("contacts_search",
              "Search Google Contacts by name, email, or phone number.",
              {"type": "object", "properties": {
                  "query": {"type": "string", "description": "Name, email, or phone to search for"},
                  "max_results": {"type": "integer", "description": "Max results (default 10)"},
              }, "required": ["query"]},
              b(contacts.search_contacts)),

        _tool("contacts_list",
              "List Google Contacts, ordered by last modified.",
              {"type": "object", "properties": {
                  "max_results": {"type": "integer", "description": "Max contacts to return (default 20)"},
              }},
              b(contacts.list_contacts)),
    ]


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------

def photos_tools(token_file=None) -> list[Tool]:
    b = partial(_bind, token_file=token_file)
    return [
        _tool("photos_search",
              "Search Google Photos by content category (people, pets, food, landscapes, selfies, travel, etc.).",
              {"type": "object", "properties": {
                  "query": {"type": "string", "description": "Content category (e.g. 'pets', 'food', 'travel')"},
                  "max_results": {"type": "integer", "description": "Max results (default 10)"},
              }, "required": ["query"]},
              b(photos.search_photos)),

        _tool("photos_list",
              "List recent photos from Google Photos.",
              {"type": "object", "properties": {
                  "max_results": {"type": "integer", "description": "Max photos (default 10)"},
              }},
              b(photos.list_photos)),

        _tool("photos_albums",
              "List Google Photos albums.",
              {"type": "object", "properties": {
                  "max_results": {"type": "integer", "description": "Max albums (default 20)"},
              }},
              b(photos.list_albums)),

        _tool("photos_album_items",
              "List photos in a specific Google Photos album.",
              {"type": "object", "properties": {
                  "album_id": {"type": "string", "description": "Album ID"},
                  "max_results": {"type": "integer", "description": "Max photos (default 20)"},
              }, "required": ["album_id"]},
              b(photos.get_album_photos)),
    ]


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def tasks_tools(token_file=None) -> list[Tool]:
    b = partial(_bind, token_file=token_file)
    return [
        _tool("tasks_lists",
              "List all Google Tasks task lists.",
              {"type": "object", "properties": {
                  "max_results": {"type": "integer", "description": "Max task lists (default 10)"},
              }},
              b(tasks.list_task_lists)),

        _tool("tasks_list",
              "List tasks in a Google Tasks list. Use tasklist_id='@default' for the default list.",
              {"type": "object", "properties": {
                  "tasklist_id": {"type": "string", "description": "Task list ID (default: '@default')"},
                  "max_results": {"type": "integer", "description": "Max tasks (default 20)"},
                  "show_completed": {"type": "boolean", "description": "Include completed tasks (default false)"},
              }},
              b(tasks.list_tasks)),

        _tool("tasks_create",
              "Create a new task in Google Tasks.",
              {"type": "object", "properties": {
                  "title": {"type": "string", "description": "Task title"},
                  "notes": {"type": "string", "description": "Task notes/details (optional)"},
                  "due": {"type": "string", "description": "Due date RFC 3339, e.g. '2026-05-10T00:00:00.000Z' (optional)"},
                  "tasklist_id": {"type": "string", "description": "Task list ID (default: '@default')"},
              }, "required": ["title"]},
              b(tasks.create_task)),

        _tool("tasks_complete",
              "Mark a Google Tasks task as completed.",
              {"type": "object", "properties": {
                  "task_id": {"type": "string", "description": "Task ID to complete"},
                  "tasklist_id": {"type": "string", "description": "Task list ID (default: '@default')"},
              }, "required": ["task_id"]},
              b(tasks.complete_task)),

        _tool("tasks_delete",
              "Delete a task from Google Tasks.",
              {"type": "object", "properties": {
                  "task_id": {"type": "string", "description": "Task ID to delete"},
                  "tasklist_id": {"type": "string", "description": "Task list ID (default: '@default')"},
              }, "required": ["task_id"]},
              b(tasks.delete_task)),
    ]


# ---------------------------------------------------------------------------
# Keep
# ---------------------------------------------------------------------------

def keep_tools() -> list[Tool]:
    return [
        _tool("keep_list",
              "List recent Google Keep notes.",
              {"type": "object", "properties": {
                  "max_results": {"type": "integer", "description": "Max notes (default 10)"},
                  "pinned_only": {"type": "boolean", "description": "Only show pinned notes (default false)"},
              }},
              keep.list_notes),

        _tool("keep_search",
              "Search Google Keep notes by text content.",
              {"type": "object", "properties": {
                  "query": {"type": "string", "description": "Text to search for in notes"},
                  "max_results": {"type": "integer", "description": "Max results (default 10)"},
              }, "required": ["query"]},
              keep.search_notes),

        _tool("keep_get",
              "Get a specific Google Keep note by its ID.",
              {"type": "object", "properties": {
                  "note_id": {"type": "string", "description": "Keep note ID"},
              }, "required": ["note_id"]},
              keep.get_note),

        _tool("keep_create_note",
              "Create a new text note in Google Keep.",
              {"type": "object", "properties": {
                  "title": {"type": "string", "description": "Note title"},
                  "text": {"type": "string", "description": "Note body text (optional)"},
                  "pinned": {"type": "boolean", "description": "Pin the note (default false)"},
              }, "required": ["title"]},
              keep.create_note),

        _tool("keep_create_list",
              "Create a new checklist in Google Keep.",
              {"type": "object", "properties": {
                  "title": {"type": "string", "description": "List title"},
                  "items": {"type": "array", "items": {"type": "string"}, "description": "Checklist items"},
                  "pinned": {"type": "boolean", "description": "Pin the list (default false)"},
              }, "required": ["title", "items"]},
              keep.create_list),

        _tool("keep_update",
              "Update an existing Google Keep note.",
              {"type": "object", "properties": {
                  "note_id": {"type": "string", "description": "Keep note ID"},
                  "title": {"type": "string", "description": "New title (optional)"},
                  "text": {"type": "string", "description": "New body text (optional)"},
                  "pinned": {"type": "boolean", "description": "Pin/unpin (optional)"},
                  "archived": {"type": "boolean", "description": "Archive/unarchive (optional)"},
              }, "required": ["note_id"]},
              keep.update_note),

        _tool("keep_delete",
              "Delete (trash) a Google Keep note.",
              {"type": "object", "properties": {
                  "note_id": {"type": "string", "description": "Keep note ID"},
              }, "required": ["note_id"]},
              keep.delete_note),
    ]


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------

def sheets_tools(token_file=None) -> list[Tool]:
    b = partial(_bind, token_file=token_file)
    return [
        _tool("sheets_read",
              "Read values from a Google Sheets spreadsheet. Range can be 'Sheet1', 'Sheet1!A1:D10', etc.",
              {"type": "object", "properties": {
                  "spreadsheet_id": {"type": "string", "description": "Google Sheets spreadsheet ID"},
                  "range": {"type": "string", "description": "Range to read (default: 'Sheet1'). E.g. 'Sheet1!A1:D10'"},
              }, "required": ["spreadsheet_id"]},
              b(sheets.read_sheet)),

        _tool("sheets_write",
              "Write values to a Google Sheets spreadsheet. Use mode='append' to add rows after existing data.",
              {"type": "object", "properties": {
                  "spreadsheet_id": {"type": "string", "description": "Google Sheets spreadsheet ID"},
                  "range": {"type": "string", "description": "Target range (e.g. 'Sheet1!A1')"},
                  "values": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}, "description": "2D array of values to write"},
                  "mode": {"type": "string", "enum": ["overwrite", "append"], "description": "'overwrite' to replace or 'append' to add rows (default: overwrite)"},
              }, "required": ["spreadsheet_id", "range", "values"]},
              b(sheets.write_sheet)),

        _tool("sheets_clear",
              "Clear values from a range in a Google Sheets spreadsheet.",
              {"type": "object", "properties": {
                  "spreadsheet_id": {"type": "string", "description": "Google Sheets spreadsheet ID"},
                  "range": {"type": "string", "description": "Range to clear (e.g. 'Sheet1!A2:D100')"},
              }, "required": ["spreadsheet_id", "range"]},
              b(sheets.clear_sheet)),

        _tool("sheets_info",
              "Get metadata about a Google Sheets spreadsheet — title and sheet names.",
              {"type": "object", "properties": {
                  "spreadsheet_id": {"type": "string", "description": "Google Sheets spreadsheet ID"},
              }, "required": ["spreadsheet_id"]},
              b(sheets.get_spreadsheet_info)),

        _tool("sheets_create",
              "Create a new Google Sheets spreadsheet.",
              {"type": "object", "properties": {
                  "title": {"type": "string", "description": "Spreadsheet title"},
                  "sheet_names": {"type": "array", "items": {"type": "string"}, "description": "Names for sheets/tabs (optional)"},
              }, "required": ["title"]},
              b(sheets.create_spreadsheet)),
    ]


# ---------------------------------------------------------------------------
# Drive
# ---------------------------------------------------------------------------

def drive_tools(token_file=None) -> list[Tool]:
    b = partial(_bind, token_file=token_file)
    return [
        _tool("drive_list",
              "List files in Google Drive, optionally within a specific folder.",
              {"type": "object", "properties": {
                  "max_results": {"type": "integer", "description": "Max files to return (default 10)"},
                  "folder_id": {"type": "string", "description": "Folder ID to list (optional, lists root if omitted)"},
              }},
              b(drive.list_files)),

        _tool("drive_search",
              "Search Google Drive files by name.",
              {"type": "object", "properties": {
                  "query": {"type": "string", "description": "Text to search for in file names"},
                  "max_results": {"type": "integer", "description": "Max results (default 10)"},
              }, "required": ["query"]},
              b(drive.search_files)),

        _tool("drive_info",
              "Get metadata about a Google Drive file by its ID.",
              {"type": "object", "properties": {
                  "file_id": {"type": "string", "description": "Drive file ID"},
              }, "required": ["file_id"]},
              b(drive.get_file_info)),

        _tool("drive_upload",
              "Upload a local file to Google Drive.",
              {"type": "object", "properties": {
                  "local_path": {"type": "string", "description": "Local file path to upload"},
                  "folder_id": {"type": "string", "description": "Target folder ID (optional)"},
                  "name": {"type": "string", "description": "Custom file name in Drive (optional, uses local filename if omitted)"},
              }, "required": ["local_path"]},
              b(drive.upload_file)),

        _tool("drive_download",
              "Download a file from Google Drive to a local path. Google Workspace files are exported (Docs→PDF, Sheets→CSV).",
              {"type": "object", "properties": {
                  "file_id": {"type": "string", "description": "Drive file ID to download"},
                  "local_path": {"type": "string", "description": "Local path to save the file"},
              }, "required": ["file_id", "local_path"]},
              b(drive.download_file)),

        _tool("drive_create_folder",
              "Create a new folder in Google Drive.",
              {"type": "object", "properties": {
                  "name": {"type": "string", "description": "Folder name"},
                  "parent_id": {"type": "string", "description": "Parent folder ID (optional)"},
              }, "required": ["name"]},
              b(drive.create_folder)),

        _tool("drive_move",
              "Move a file to a different folder in Google Drive.",
              {"type": "object", "properties": {
                  "file_id": {"type": "string", "description": "File ID to move"},
                  "new_parent_id": {"type": "string", "description": "Target folder ID"},
              }, "required": ["file_id", "new_parent_id"]},
              b(drive.move_file)),

        _tool("drive_delete",
              "Move a Google Drive file to trash.",
              {"type": "object", "properties": {
                  "file_id": {"type": "string", "description": "File ID to trash"},
              }, "required": ["file_id"]},
              b(drive.delete_file)),
    ]


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------

def youtube_tools(token_file=None) -> list[Tool]:
    b = partial(_bind, token_file=token_file)
    return [
        _tool("youtube_search",
              "Search YouTube for videos. Returns video IDs, titles, channels, and URLs.",
              {"type": "object", "properties": {
                  "query": {"type": "string", "description": "Search query"},
                  "max_results": {"type": "integer", "description": "Max results (default 5)"},
              }, "required": ["query"]},
              b(youtube.search_videos)),

        _tool("youtube_video_info",
              "Get detailed info about a YouTube video (title, channel, views, likes, duration, description).",
              {"type": "object", "properties": {
                  "video_id": {"type": "string", "description": "YouTube video ID (e.g. 'dQw4w9WgXcQ')"},
              }, "required": ["video_id"]},
              b(youtube.get_video_info)),

        _tool("youtube_playlists",
              "List the user's YouTube playlists.",
              {"type": "object", "properties": {
                  "max_results": {"type": "integer", "description": "Max playlists (default 10)"},
              }},
              b(youtube.list_playlists)),

        _tool("youtube_playlist_items",
              "List videos in a YouTube playlist.",
              {"type": "object", "properties": {
                  "playlist_id": {"type": "string", "description": "Playlist ID"},
                  "max_results": {"type": "integer", "description": "Max videos (default 20)"},
              }, "required": ["playlist_id"]},
              b(youtube.get_playlist_items)),

        _tool("youtube_add_to_playlist",
              "Add a video to a YouTube playlist.",
              {"type": "object", "properties": {
                  "playlist_id": {"type": "string", "description": "Playlist ID"},
                  "video_id": {"type": "string", "description": "Video ID to add"},
              }, "required": ["playlist_id", "video_id"]},
              b(youtube.add_to_playlist)),

        _tool("youtube_create_playlist",
              "Create a new YouTube playlist.",
              {"type": "object", "properties": {
                  "title": {"type": "string", "description": "Playlist title"},
                  "description": {"type": "string", "description": "Playlist description (optional)"},
                  "privacy": {"type": "string", "enum": ["private", "public", "unlisted"], "description": "Privacy status (default: private)"},
              }, "required": ["title"]},
              b(youtube.create_playlist)),

        _tool("youtube_transcript",
              "Get the transcript/captions of a YouTube video. Returns the text content of captions (prefers English).",
              {"type": "object", "properties": {
                  "video_id": {"type": "string", "description": "YouTube video ID"},
                  "language": {"type": "string", "description": "Language code (default: 'en')"},
              }, "required": ["video_id"]},
              b(youtube.get_transcript)),

        _tool("youtube_download_video",
              "Download a YouTube video as MP4 file. Saves to ~/Downloads by default.",
              {"type": "object", "properties": {
                  "video_id": {"type": "string", "description": "YouTube video ID or full URL"},
                  "resolution": {"type": "string", "description": "Desired resolution: '720p', '1080p', 'best' (default: 'best')"},
                  "output_dir": {"type": "string", "description": "Directory to save the file (default: ~/Downloads)"},
              }, "required": ["video_id"]},
              b(youtube.download_video)),

        _tool("youtube_download_audio",
              "Download a YouTube video as MP3 audio file. Saves to ~/Downloads by default.",
              {"type": "object", "properties": {
                  "video_id": {"type": "string", "description": "YouTube video ID or full URL"},
                  "output_dir": {"type": "string", "description": "Directory to save the file (default: ~/Downloads)"},
              }, "required": ["video_id"]},
              b(youtube.download_audio)),

        _tool("youtube_formats",
              "List available download formats/resolutions for a YouTube video.",
              {"type": "object", "properties": {
                  "video_id": {"type": "string", "description": "YouTube video ID or full URL"},
              }, "required": ["video_id"]},
              b(youtube.get_formats)),
    ]


# ---------------------------------------------------------------------------
# All tools
# ---------------------------------------------------------------------------

def build_tools(token_file=None, **_kwargs) -> list[Tool]:
    """Return all Google tools, optionally bound to a specific token file.

    Args:
        token_file: Path to a specific Google OAuth token.json.
                    If None, uses the global default token.
    """
    return (
        gmail_tools(token_file) +
        calendar_tools(token_file) +
        docs_tools(token_file) +
        contacts_tools(token_file) +
        photos_tools(token_file) +
        tasks_tools(token_file) +
        keep_tools() +
        sheets_tools(token_file) +
        drive_tools(token_file) +
        youtube_tools(token_file)
    )
