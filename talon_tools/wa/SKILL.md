---
description: Read, search, and send WhatsApp messages across chats and groups
dependencies:
  - wacli
---

# WhatsApp

Interact with WhatsApp via the wacli CLI. Supports reading messages, searching conversations, sending messages, and managing groups.

## When to Use

- "Show me my latest WhatsApp messages"
- "What did [person] say?"
- "Summarise messages from [group]"
- "Send [person] a message saying..."
- "Any unread WhatsApp messages?"
- "What's happening in [group name]?"
- Periodic digests of unread chats/groups

## Installation & Invocation

```bash
pip install 'talon-tools[wa]'
```

Also requires the `wacli` binary (not a Python package):

```bash
# See https://github.com/nicois/wacli for install instructions
# Then link your WhatsApp account:
wacli auth
```

Session stored in `~/.wacli/` by default.

Load and call:

```python
import asyncio
from talon_tools.wa.tools import build_tools

tools = {t.name: t for t in build_tools()}

# List unread chats
result = asyncio.run(tools["list_whatsapp_chats"].handler({"unread": True}))
print(result.content)

# Send a message
result = asyncio.run(tools["send_whatsapp_message"].handler({"to": "+1234567890", "message": "Hello!"}))
print(result.content)
```

### Without Python (wacli CLI directly)

The Python package is just a thin wrapper around `wacli`. You can call it directly:

```bash
# List unread chats
wacli chats --unread --json | jq

# Get messages from a chat
wacli messages 1234567890@s.whatsapp.net --limit 20 --json | jq

# Search messages
wacli search "meeting tomorrow" --json | jq

# Send a message
wacli send 1234567890@s.whatsapp.net "Hello!"

# Send a file
wacli send 1234567890@s.whatsapp.net --file /path/to/image.jpg --caption "Check this out"
```

## Credentials

WhatsApp account linked via `wacli auth`. No API keys needed.

## Available Tools

| Tool | Purpose |
|------|---------|
| `send_whatsapp_message` | Send text (supports reply and @mentions) |
| `send_whatsapp_file` | Send image/video/audio/document |
| `send_whatsapp_reaction` | React to a message with emoji |
| `list_whatsapp_chats` | List chats (filter: unread, pinned, query) |
| `get_whatsapp_messages` | Get recent messages from a chat |
| `search_whatsapp_messages` | Full-text search (filter: date, media, chat) |
| `get_whatsapp_message_context` | Surrounding messages for thread context |
| `search_whatsapp_contacts` | Find contacts by name/phone/JID |
| `list_whatsapp_groups` | List groups (filter by name) |
| `get_whatsapp_group_info` | Group details (members, description) |
| `mark_whatsapp_read` | Mark a chat as read |

## Workflow: Catch Up on Messages

1. `list_whatsapp_chats` with `unread: true` to find chats with new messages
2. `get_whatsapp_messages` for each unread chat
3. Summarise by chat/person

## Workflow: Find a Conversation

1. `search_whatsapp_messages` with keywords
2. `get_whatsapp_message_context` for surrounding context

## Workflow: Group Summary

1. `list_whatsapp_chats` to find the group
2. `get_whatsapp_messages` with the group JID
3. Summarise key topics, decisions, and action items

## Workflow: Send a Message

1. `list_whatsapp_chats` to find the recipient's JID if needed
2. `send_whatsapp_message` with the JID and text
3. For replies, include `reply_to` with the target message ID

## Notes

- JIDs: `1234567890@s.whatsapp.net` (contacts) or `120363...@g.us` (groups)
- Phone numbers in E.164 format: `+1234567890`
- Date filters use `YYYY-MM-DD` format
- Empty reaction string removes a previous reaction
- Only synced messages in the local wacli store are searchable
