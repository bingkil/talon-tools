---
description: Gmail, Calendar, Docs, Contacts, Photos, Tasks, Keep, Sheets, Drive, and YouTube
dependencies:
  - talon-tools[google]
---

# Google Workspace

Comprehensive Google Workspace integration covering Gmail, Calendar, Docs, Contacts, Photos, Tasks, Keep, Sheets, Drive, and YouTube.

## When to Use

- "Check my email" / "Any new emails?"
- "What's on my calendar today?"
- "Send an email to..."
- "Create a calendar event for..."
- "Find that Google Doc about..."
- "What tasks do I have?"
- "Search my contacts for..."
- "Show my recent photos"
- "What's in this spreadsheet?"
- "Search YouTube for..."

## Installation & Invocation

```bash
pip install 'talon-tools[google]'
```

First-time setup triggers a browser OAuth flow. The token is stored in `token.json` for reuse.

Load and call:

```python
import asyncio
from talon_tools.google.tools import build_tools

tools = {t.name: t for t in build_tools()}

# Check inbox
result = asyncio.run(tools["gmail_inbox"].handler({}))
print(result.content)

# Search calendar
result = asyncio.run(tools["calendar_list"].handler({}))
print(result.content)
```

Optional: pass `token_file="/path/to/token.json"` to `build_tools()` for multi-account setups.

### Without Python

Google APIs require OAuth 2.0 tokens. If you already have an access token (from the Python setup or Google Cloud Console):

```bash
# List recent emails
curl -s -H "Authorization: Bearer $GOOGLE_TOKEN" \
  "https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=10" | jq

# Get calendar events
curl -s -H "Authorization: Bearer $GOOGLE_TOKEN" \
  "https://www.googleapis.com/calendar/v3/calendars/primary/events?maxResults=10&timeMin=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | jq '.items[] | {summary, start: .start.dateTime}'

# Search Drive
curl -s -H "Authorization: Bearer $GOOGLE_TOKEN" \
  "https://www.googleapis.com/drive/v3/files?q=name+contains+'meeting'" | jq '.files[] | {name, id, mimeType}'
```

Note: Getting the initial OAuth token requires the Python setup (`python -m talon_tools.cli setup google`) or manual OAuth via Google Cloud Console. Tokens expire after 1 hour and need refresh.

## Credentials

Requires Google OAuth 2.0 token. On first call, a browser window opens for authorization. The token is then cached to disk and refreshed automatically.

## Available Tools

### Gmail
| Tool | Purpose |
|------|---------|
| `gmail_inbox` | List recent emails with optional search query |
| `gmail_read` | Read full email content by message ID (includes attachment metadata) |
| `gmail_search` | Search emails using Gmail query syntax |
| `gmail_send` | Send email with optional attachments |
| `gmail_draft` | Create a draft email |
| `gmail_reply` | Reply to an email, preserving the thread (supports reply-all) |
| `gmail_forward` | Forward an email to another address |
| `gmail_get_thread` | Read all messages in a conversation thread |
| `gmail_mark_read` | Mark an email as read |
| `gmail_mark_unread` | Mark an email as unread |
| `gmail_archive` | Archive an email (remove from inbox) |
| `gmail_trash` | Move an email to trash |
| `gmail_star` | Star an email |
| `gmail_unstar` | Remove star from an email |
| `gmail_download_attachment` | Download an email attachment to disk |
| `gmail_list_labels` | List all labels (system + user-created) with IDs |
| `gmail_add_label` | Apply a label to an email |
| `gmail_remove_label` | Remove a label from an email |
| `gmail_create_filter` | Create a filter to auto-process future emails matching criteria |

### Calendar
| Tool | Purpose |
|------|---------|
| `calendar_list` | List upcoming events (default 7 days) |
| `calendar_get` | Get event details by ID |
| `calendar_create` | Create new calendar event |

### Google Docs
| Tool | Purpose |
|------|---------|
| `docs_read` | Read a Google Doc by document ID |
| `docs_search` | Search Google Docs by name |
| `docs_list` | List recently modified docs |

### Contacts
| Tool | Purpose |
|------|---------|
| `contacts_search` | Search by name, email, or phone |
| `contacts_list` | List contacts by last modified |

### Photos
| Tool | Purpose |
|------|---------|
| `photos_search` | Search by content category |
| `photos_list` | List recent photos |
| `photos_albums` | List albums |
| `photos_album_items` | List photos in an album |

### Tasks
| Tool | Purpose |
|------|---------|
| `tasks_lists` | List all task lists |
| `tasks_list` | List tasks (with completed filter) |
| `tasks_create` | Create a new task |
| `tasks_complete` | Mark task as completed |
| `tasks_delete` | Delete a task |

### Keep
| Tool | Purpose |
|------|---------|
| `keep_list` | List recent notes |
| `keep_search` | Search notes by text |
| `keep_get` | Get note by ID |
| `keep_create_note` | Create a new text note |
| `keep_create_list` | Create a new checklist |
| `keep_update` | Update an existing note |
| `keep_delete` | Delete (trash) a note |

### Sheets
| Tool | Purpose |
|------|---------|
| `sheets_read` | Read values from a spreadsheet (specify range) |
| `sheets_write` | Write values to a spreadsheet (overwrite or append) |
| `sheets_clear` | Clear values from a range |
| `sheets_info` | Get spreadsheet metadata (title, sheet names) |
| `sheets_create` | Create a new spreadsheet |

### Drive
| Tool | Purpose |
|------|---------|
| `drive_list` | List files (optionally within a folder) |
| `drive_search` | Search files by name |
| `drive_info` | Get file metadata by ID |
| `drive_upload` | Upload a local file to Drive |
| `drive_download` | Download a file from Drive |
| `drive_create_folder` | Create a new folder |
| `drive_move` | Move a file to a different folder |
| `drive_delete` | Move a file to trash |

### YouTube
| Tool | Purpose |
|------|---------|
| `youtube_search` | Search videos by query |
| `youtube_video_info` | Get video details (title, views, duration) |
| `youtube_playlists` | List user's playlists |
| `youtube_playlist_items` | List videos in a playlist |
| `youtube_add_to_playlist` | Add a video to a playlist |
| `youtube_create_playlist` | Create a new playlist |
| `youtube_transcript` | Get video transcript/captions |
| `youtube_download_video` | Download video as MP4 |
| `youtube_download_audio` | Download video as MP3 |
| `youtube_formats` | List available download formats |

## Workflow: Morning Briefing

1. `gmail_inbox` — check unread emails
2. `calendar_list` — today's events
3. `tasks_list` — pending tasks
4. Summarise everything in a quick digest

## Workflow: Find and Read a Document

1. `docs_search` or `drive_search` by name
2. `docs_read` with the document ID
3. Summarise or extract key points

## Notes

- Gmail search uses Gmail query syntax: `from:someone`, `is:unread`, `has:attachment`, `after:2026/01/01`
- Calendar defaults to 7-day lookahead
- Photos search supports categories: pets, food, travel, selfies, etc.
- Keep uses unofficial API (gkeepapi) — reliable but not Google-supported
