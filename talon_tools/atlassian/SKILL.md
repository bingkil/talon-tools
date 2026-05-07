---
description: Search, create, and manage Jira issues and Confluence pages
dependencies:
  - talon-tools[atlassian]
---

# Atlassian (Jira & Confluence)

Interact with Jira and Confluence via the Atlassian Cloud API. Search issues, create tickets, transition workflows, and read or create Confluence pages.

## When to Use

- "Find open bugs in project X"
- "Create a Jira ticket for..."
- "What's the status of PROJ-123?"
- "Search Confluence for onboarding docs"
- "Add a comment to PROJ-456"
- "Assign this issue to..."
- "Move PROJ-789 to In Progress"

## Installation & Invocation

Install the package:

```bash
pip install 'talon-tools[atlassian]'
```

Set environment variables (or use a `.env` / `credentials.yaml` file):

```bash
export JIRA_URL=https://company.atlassian.net
export JIRA_USERNAME=you@company.com
export JIRA_API_TOKEN=your-api-token
```

Load tools in Python and register with your agent framework:

```python
from talon_tools.atlassian.tools import build_tools

tools = build_tools()
# Each tool has: .name, .description, .parameters (JSON Schema), .handler(args) -> ToolResult
```

Or call a tool directly:

```python
import asyncio
from talon_tools.atlassian.tools import build_tools

tools = {t.name: t for t in build_tools()}
result = asyncio.run(tools["jira_search"].handler({"jql": "project = PROJ AND status = Open"}))
print(result.content)
```

### Without Python (curl)

```bash
# Search issues
curl -s -u "$JIRA_USERNAME:$JIRA_API_TOKEN" \
  "$JIRA_URL/rest/api/3/search?jql=project%20%3D%20PROJ%20AND%20status%20%3D%20Open" | jq

# Get issue
curl -s -u "$JIRA_USERNAME:$JIRA_API_TOKEN" \
  "$JIRA_URL/rest/api/3/issue/PROJ-123" | jq

# Create issue
curl -s -X POST -u "$JIRA_USERNAME:$JIRA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"fields":{"project":{"key":"PROJ"},"summary":"Bug title","issuetype":{"name":"Bug"}}}' \
  "$JIRA_URL/rest/api/3/issue" | jq

# Add comment
curl -s -X POST -u "$JIRA_USERNAME:$JIRA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"body":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"My comment"}]}]}}' \
  "$JIRA_URL/rest/api/3/issue/PROJ-123/comment" | jq
```

## Credentials

- `JIRA_URL` — Atlassian instance URL (e.g., `https://company.atlassian.net`)
- `JIRA_USERNAME` — Atlassian email address
- `JIRA_API_TOKEN` — API token from https://id.atlassian.com/manage-profile/security/api-tokens

## Available Tools

| Tool | Purpose |
|------|---------|
| `jira_search` | Search issues using JQL (e.g., `project = PROJ AND status = Open`) |
| `jira_get_issue` | Get full details of an issue by key |
| `jira_create_issue` | Create a new issue (project, summary, type, description) |
| `jira_update_issue` | Update issue fields (summary, description, labels, priority) |
| `jira_transition` | Change issue status/workflow state |
| `jira_add_comment` | Add a comment to an issue |
| `jira_assign` | Assign issue to a user |
| `confluence_search` | Search Confluence pages using CQL |
| `confluence_get_page` | Get page content by ID or title |
| `confluence_create_page` | Create a new Confluence page |
| `confluence_update_page` | Update existing page content |
| `confluence_get_spaces` | List available Confluence spaces |

## Workflow: Triage Open Issues

1. `jira_search` with JQL: `project = PROJ AND status = Open ORDER BY priority DESC`
2. Review each issue with `jira_get_issue`
3. Assign, comment, or transition as needed

## Workflow: Create and Track a Task

1. `jira_create_issue` with project key, summary, and description
2. `jira_assign` to the right person
3. `jira_transition` to move through workflow states

## Notes

- JQL reference: https://support.atlassian.com/jira-software-cloud/docs/use-advanced-search-with-jql/
- Comments are limited to last 5 per issue for brevity
- CQL reference for Confluence: https://developer.atlassian.com/cloud/confluence/cql/
