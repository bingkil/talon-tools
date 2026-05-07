---
description: Outlook email, calendar, and Microsoft Teams messages via Microsoft Graph
dependencies:
  - talon-tools[microsoft]
---

# Microsoft 365

Integration with Outlook Mail, Outlook Calendar, and Microsoft Teams via Microsoft Graph API.

## When to Use

- "Check my Outlook inbox"
- "Any new emails?"
- "What meetings do I have today?"
- "Read that email from..."
- "What's happening in Teams?"
- "Show messages from the engineering channel"
- "Any new Teams chats?"

## Installation & Invocation

```bash
pip install 'talon-tools[microsoft]'
```

First-time setup triggers a browser OAuth flow. Token is cached to disk.

Optional environment variables (defaults work for most tenants):

```bash
export MS_CLIENT_ID=your-client-id    # defaults to Microsoft Graph PowerShell ID
export MS_TENANT_ID=your-tenant-id    # defaults to "common"
```

Load and call:

```python
import asyncio
from talon_tools.microsoft.tools import build_tools

tools = {t.name: t for t in build_tools()}

# Check inbox
result = asyncio.run(tools["outlook_inbox"].handler({}))
print(result.content)

# List Teams chats
result = asyncio.run(tools["teams_list_chats"].handler({}))
print(result.content)
```

### Without Python

Microsoft Graph APIs require OAuth tokens. If you already have an access token:

```bash
# List recent emails
curl -s -H "Authorization: Bearer $MS_TOKEN" \
  "https://graph.microsoft.com/v1.0/me/messages?\$top=10&\$select=subject,from,receivedDateTime" | jq '.value[] | {subject, from: .from.emailAddress.name, date: .receivedDateTime}'

# Calendar events
curl -s -H "Authorization: Bearer $MS_TOKEN" \
  "https://graph.microsoft.com/v1.0/me/calendarView?startDateTime=$(date -u +%Y-%m-%dT00:00:00Z)&endDateTime=$(date -u +%Y-%m-%dT23:59:59Z)" | jq '.value[] | {subject, start: .start.dateTime}'

# List Teams chats
curl -s -H "Authorization: Bearer $MS_TOKEN" \
  "https://graph.microsoft.com/v1.0/me/chats?\$top=10" | jq '.value[] | {topic, chatType, lastUpdatedDateTime}'
```

Note: Getting the initial OAuth token requires the Python setup (`python -m talon_tools.cli setup microsoft`) or manual device code flow via Azure Portal.

## Credentials

- `MS_CLIENT_ID` — Azure AD client ID (defaults to Microsoft Graph PowerShell, widely pre-consented)
- `MS_TENANT_ID` — Azure AD tenant (defaults to "common" for multi-tenant)
- `MS_TOKEN_FILE` — Token cache path (auto-managed)

## Available Tools

### Outlook Mail
| Tool | Purpose |
|------|---------|
| `outlook_inbox` | List recent emails with optional OData filter |
| `outlook_read` | Read full email content by message ID |
| `outlook_search` | Search emails (natural language + KQL) |

### Outlook Calendar
| Tool | Purpose |
|------|---------|
| `outlook_calendar_list` | List upcoming calendar events |
| `outlook_calendar_get` | Get event details by ID |

### Teams
| Tool | Purpose |
|------|---------|
| `teams_list_teams` | List teams you're a member of |
| `teams_list_channels` | List channels in a team |
| `teams_channel_messages` | Read recent channel messages |
| `teams_list_chats` | List 1:1 and group chats |
| `teams_chat_messages` | Read messages from a chat |

## Workflow: Morning Briefing

1. `outlook_inbox` — check latest emails
2. `outlook_calendar_list` — today's meetings
3. `teams_list_chats` — recent Teams conversations
4. Summarise into a digest

## Workflow: Catch Up on a Teams Channel

1. `teams_list_teams` — find the team
2. `teams_list_channels` — find the channel
3. `teams_channel_messages` — read recent messages
4. Summarise key discussions

## Notes

- Outlook search supports KQL: `from:someone`, `subject:keyword`, `hasAttachment:true`
- Default client ID works for most Microsoft 365 tenants without admin consent
- Token is cached to disk and refreshed automatically
