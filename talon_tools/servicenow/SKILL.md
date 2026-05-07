---
description: List your ServiceNow cases and change requests
dependencies:
  - talon-tools[servicenow]
---

# ServiceNow

Query your ServiceNow cases (CSxxxxxx) and change requests (CHGxxxxxxx) directly from the ServiceNow API.

## When to Use

- "Show my open cases"
- "Any pending change requests?"
- "What's the status of my ServiceNow tickets?"
- "List my closed cases"
- Daily standup / work tracking

## Installation & Invocation

```bash
pip install 'talon-tools[servicenow]'
```

Set environment variables:

```bash
export SERVICENOW_URL=https://company.service-now.com
export SERVICENOW_USERNAME=your-username
export SERVICENOW_PASSWORD=your-password
```

Load and call:

```python
import asyncio
from talon_tools.servicenow.tools import build_tools

tools = {t.name: t for t in build_tools()}
result = asyncio.run(tools["my_cases"].handler({"status": "open"}))
print(result.content)
```

### Without Python (curl)

```bash
# List my open cases
curl -s -u "$SERVICENOW_USERNAME:$SERVICENOW_PASSWORD" \
  "$SERVICENOW_URL/api/now/table/sn_customerservice_case?sysparm_query=active=true^opened_by.user_name=$SERVICENOW_USERNAME&sysparm_display_value=true&sysparm_limit=20" | jq '.result[] | {number, state, short_description, priority}'

# List my change requests
curl -s -u "$SERVICENOW_USERNAME:$SERVICENOW_PASSWORD" \
  "$SERVICENOW_URL/api/now/table/change_request?sysparm_query=opened_by.user_name=$SERVICENOW_USERNAME&sysparm_display_value=true&sysparm_limit=20" | jq '.result[] | {number, state, short_description, risk}'
```

## Credentials

- `SERVICENOW_URL` — Instance URL (e.g., `https://company.service-now.com`)
- `SERVICENOW_USERNAME` — ServiceNow username
- `SERVICENOW_PASSWORD` — ServiceNow password

## Available Tools

| Tool | Purpose |
|------|---------|
| `my_cases` | List your ServiceNow cases (open or closed) |
| `my_change_requests` | List your change requests (open or closed) |

## Parameters

- `status` — `open` (default) or `closed`
- `limit` — Max results (default 20)

## Notes

- Filters by your username automatically
- Cases sorted by creation date (newest first)
- Change requests include risk level and scheduled dates
- Uses Basic HTTP authentication
