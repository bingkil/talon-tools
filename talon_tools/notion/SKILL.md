---
description: Search, read, create, and update Notion pages and databases
dependencies:
  - talon-tools[notion]
---

# Notion

Interact with Notion workspaces — search pages, read content, create new pages, update existing ones, and query databases.

## When to Use

- "Find my meeting notes in Notion"
- "Create a new page in Notion"
- "What's in my project tracker database?"
- "Update the status on that Notion page"
- "Search Notion for onboarding docs"

## Installation & Invocation

```bash
pip install 'talon-tools[notion]'
```

Set environment variable:

```bash
export NOTION_TOKEN=secret_abc123
```

Get your token from https://www.notion.so/my-integrations — the integration must be connected to the pages/databases you want to access.

Load and call:

```python
import asyncio
from talon_tools.notion.tools import build_tools

tools = {t.name: t for t in build_tools()}
result = asyncio.run(tools["notion_search"].handler({"query": "meeting notes"}))
print(result.content)
```

### Without Python (curl)

```bash
# Search pages
curl -s -X POST "https://api.notion.com/v1/search" \
  -H "Authorization: Bearer $NOTION_TOKEN" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{"query": "meeting notes"}' | jq '.results[] | {title: .properties.title.title[0].plain_text, url: .url}'

# Read a page (as blocks)
curl -s "https://api.notion.com/v1/blocks/PAGE_ID/children" \
  -H "Authorization: Bearer $NOTION_TOKEN" \
  -H "Notion-Version: 2022-06-28" | jq

# Query a database
curl -s -X POST "https://api.notion.com/v1/databases/DB_ID/query" \
  -H "Authorization: Bearer $NOTION_TOKEN" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{}' | jq '.results[] | {id: .id, url: .url}'
```

## Credentials

- `NOTION_TOKEN` — Internal integration token from https://www.notion.so/my-integrations

## Available Tools

| Tool | Purpose |
|------|---------|
| `notion_search` | Search pages and databases by title |
| `notion_read_page` | Read page content as markdown |
| `notion_create_page` | Create a new page with markdown content |
| `notion_update_page` | Update page content via find-and-replace |
| `notion_query_database` | Query a database with filters and sorts |

## Workflow: Find and Read a Page

1. `notion_search` with keywords to find the page
2. `notion_read_page` with the page ID to read its content

## Workflow: Create a New Page

1. `notion_search` to find the parent page or database
2. `notion_create_page` with parent ID, title, and markdown content

## Workflow: Query a Database

1. `notion_search` with `filter: database` to find the database
2. `notion_query_database` with database ID and optional filter/sort JSON

## Notes

- Content is returned as markdown
- Filters and sorts for database queries use Notion's JSON filter syntax
- The integration must be explicitly shared with each page/database it needs to access
