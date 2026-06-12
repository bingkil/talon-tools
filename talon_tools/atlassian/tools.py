"""Jira and Confluence tool definitions for Talon agents."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from talon_tools import Tool, ToolResult
from talon_tools.credentials import CredentialRequirement, validate, get as cred

from .client import JiraClient, ConfluenceClient
from .confluence_parse import parse as confluence_parse, extract_refs

log = logging.getLogger(__name__)

CREDENTIALS = [
    CredentialRequirement("JIRA_URL", "Jira instance URL (e.g. https://company.atlassian.net)"),
    CredentialRequirement("JIRA_USERNAME", "Jira username or email address"),
    CredentialRequirement("JIRA_API_TOKEN", "Jira API token", hint="https://id.atlassian.com/manage-profile/security/api-tokens"),
]


def _format_issue_summary(issue: dict) -> str:
    """Format a single issue from search results."""
    key = issue.get("key", "")
    fields = issue.get("fields", {})
    summary = fields.get("summary", "")
    status = fields.get("status", {}).get("name", "")
    priority = fields.get("priority", {}).get("name", "") if fields.get("priority") else ""
    itype = fields.get("issuetype", {}).get("name", "")
    assignee = fields.get("assignee", {}).get("displayName", "Unassigned") if fields.get("assignee") else "Unassigned"
    parts = [f"**{key}** {summary}"]
    tags = []
    if status:
        tags.append(status)
    if priority:
        tags.append(priority)
    if itype:
        tags.append(itype)
    if tags:
        parts.append(f"[{' · '.join(tags)}]")
    parts.append(f"→ {assignee}")
    return " — ".join(parts)


def _format_issue_detail(issue: dict) -> str:
    """Format full issue details."""
    key = issue.get("key", "")
    fields = issue.get("fields", {})
    summary = fields.get("summary", "")
    status = fields.get("status", {}).get("name", "")
    priority = fields.get("priority", {}).get("name", "") if fields.get("priority") else ""
    itype = fields.get("issuetype", {}).get("name", "")
    assignee = fields.get("assignee", {}).get("displayName", "Unassigned") if fields.get("assignee") else "Unassigned"
    description = fields.get("description") or "(no description)"
    labels = fields.get("labels", [])
    created = fields.get("created", "")[:10]
    updated = fields.get("updated", "")[:10]

    lines = [
        f"# {key}: {summary}",
        f"**Type:** {itype} | **Status:** {status} | **Priority:** {priority}",
        f"**Assignee:** {assignee} | **Labels:** {', '.join(labels) if labels else 'none'}",
        f"**Created:** {created} | **Updated:** {updated}",
        "",
        "## Description",
        description,
    ]

    comments = fields.get("comment", {}).get("comments", [])
    if comments:
        lines.append("")
        lines.append(f"## Comments ({len(comments)})")
        for c in comments[-5:]:  # Last 5 comments
            author = c.get("author", {}).get("displayName", "Unknown")
            body = c.get("body", "")
            date = c.get("created", "")[:10]
            lines.append(f"\n**{author}** ({date}):\n{body}")

    return "\n".join(lines)


def build_tools(**_kwargs) -> list[Tool]:
    """Return Jira and Confluence tools for agent use."""
    validate("atlassian", CREDENTIALS)

    # Capture credentials eagerly while agent context is guaranteed set
    _url = cred("JIRA_URL")
    _username = cred("JIRA_USERNAME")
    _token = cred("JIRA_API_TOKEN")

    _jira_client: JiraClient | None = None
    _confluence_client: ConfluenceClient | None = None

    def _get_jira() -> JiraClient:
        nonlocal _jira_client
        if _jira_client is None:
            _jira_client = JiraClient(url=_url, username=_username, token=_token)
        return _jira_client

    def _get_confluence() -> ConfluenceClient:
        nonlocal _confluence_client
        if _confluence_client is None:
            _confluence_client = ConfluenceClient(url=_url, username=_username, token=_token)
        return _confluence_client

    async def search_handler(args: dict[str, Any]) -> ToolResult:
        jql = args.get("jql", "")
        if not jql:
            return ToolResult(content="Error: jql is required", is_error=True)
        limit = args.get("limit", 20)
        try:
            result = await _get_jira().search(jql, limit=limit)
            issues = result.get("issues", [])
            if not issues:
                return ToolResult(content="No issues found.")
            total = result.get("total", len(issues))
            lines = [f"Found {total} issue(s), showing {len(issues)}:\n"]
            for issue in issues:
                lines.append(f"- {_format_issue_summary(issue)}")
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("jira_search failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    async def get_issue_handler(args: dict[str, Any]) -> ToolResult:
        key = args.get("issue_key", "")
        if not key:
            return ToolResult(content="Error: issue_key is required", is_error=True)
        try:
            issue = await _get_jira().get_issue(key)
            return ToolResult(content=_format_issue_detail(issue))
        except Exception as e:
            log.exception("jira_get_issue failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    async def create_issue_handler(args: dict[str, Any]) -> ToolResult:
        project = args.get("project", "")
        summary = args.get("summary", "")
        if not project or not summary:
            return ToolResult(content="Error: project and summary are required", is_error=True)
        issue_type = args.get("issue_type", "Task")
        description = args.get("description", "")
        try:
            result = await _get_jira().create_issue(project, summary, issue_type, description)
            key = result.get("key", "")
            return ToolResult(content=f"Created: {key}")
        except Exception as e:
            log.exception("jira_create_issue failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    async def update_issue_handler(args: dict[str, Any]) -> ToolResult:
        key = args.get("issue_key", "")
        if not key:
            return ToolResult(content="Error: issue_key is required", is_error=True)
        fields: dict[str, Any] = {}
        if args.get("summary"):
            fields["summary"] = args["summary"]
        if args.get("description"):
            fields["description"] = args["description"]
        if args.get("labels"):
            labels = [l.strip() for l in args["labels"].split(",")]
            fields["labels"] = labels
        if args.get("priority"):
            fields["priority"] = {"name": args["priority"]}
        if args.get("fields"):
            try:
                extra = json.loads(args["fields"])
                fields.update(extra)
            except json.JSONDecodeError as e:
                return ToolResult(content=f"Error: invalid fields JSON: {e}", is_error=True)
        if not fields:
            return ToolResult(content="Error: no fields to update", is_error=True)
        try:
            await _get_jira().update_fields(key, fields)
            return ToolResult(content=f"Updated {key}")
        except Exception as e:
            log.exception("jira_update_issue failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    async def transition_handler(args: dict[str, Any]) -> ToolResult:
        key = args.get("issue_key", "")
        status = args.get("status", "")
        if not key or not status:
            return ToolResult(content="Error: issue_key and status are required", is_error=True)
        try:
            await _get_jira().transition(key, status)
            return ToolResult(content=f"Transitioned {key} to {status}")
        except Exception as e:
            log.exception("jira_transition failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    async def comment_handler(args: dict[str, Any]) -> ToolResult:
        key = args.get("issue_key", "")
        comment = args.get("comment", "")
        if not key or not comment:
            return ToolResult(content="Error: issue_key and comment are required", is_error=True)
        try:
            await _get_jira().add_comment(key, comment)
            return ToolResult(content=f"Comment added to {key}")
        except Exception as e:
            log.exception("jira_add_comment failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    async def assign_handler(args: dict[str, Any]) -> ToolResult:
        key = args.get("issue_key", "")
        account_id = args.get("account_id", "")
        if not key or not account_id:
            return ToolResult(content="Error: issue_key and account_id are required", is_error=True)
        try:
            await _get_jira().assign(key, account_id)
            return ToolResult(content=f"Assigned {key} to {account_id}")
        except Exception as e:
            log.exception("jira_assign failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    async def clone_issue_handler(args: dict[str, Any]) -> ToolResult:
        source_key = args.get("issue_key", "")
        if not source_key:
            return ToolResult(content="Error: issue_key is required", is_error=True)
        try:
            source = await _get_jira().get_issue_full(source_key)
            sf = source.get("fields", {})
            project = sf.get("project", {}).get("key", "")
            summary = args.get("summary") or sf.get("summary", "")
            issue_type = sf.get("issuetype", {}).get("name", "Task")
            description = sf.get("description") or ""

            # Build fields for the clone
            create_fields: dict[str, Any] = {
                "project": {"key": project},
                "summary": summary,
                "issuetype": {"name": issue_type},
            }
            if description:
                create_fields["description"] = description
            # Copy labels
            if sf.get("labels"):
                create_fields["labels"] = sf["labels"]
            # Copy priority
            if sf.get("priority"):
                create_fields["priority"] = {"name": sf["priority"]["name"]}
            # Copy assignee
            if sf.get("assignee"):
                create_fields["assignee"] = {"id": sf["assignee"]["accountId"]}
            # Apply overrides from fields JSON
            if args.get("fields"):
                try:
                    extra = json.loads(args["fields"])
                    create_fields.update(extra)
                except json.JSONDecodeError as e:
                    return ToolResult(content=f"Error: invalid fields JSON: {e}", is_error=True)

            result = await asyncio.to_thread(_get_jira()._jira.create_issue, create_fields)
            new_key = result.get("key", "")

            # Link clone to original
            link_type = args.get("link_type", "Cloners")
            try:
                await _get_jira().link_issues(new_key, source_key, link_type)
            except Exception:
                log.warning("Could not create link between %s and %s", new_key, source_key)

            return ToolResult(content=f"Cloned {source_key} → {new_key}")
        except Exception as e:
            log.exception("jira_clone_issue failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    async def link_issues_handler(args: dict[str, Any]) -> ToolResult:
        inward = args.get("inward_issue", "")
        outward = args.get("outward_issue", "")
        link_type = args.get("link_type", "Relates")
        if not inward or not outward:
            return ToolResult(content="Error: inward_issue and outward_issue are required", is_error=True)
        try:
            await _get_jira().link_issues(inward, outward, link_type)
            return ToolResult(content=f"Linked {inward} ←[{link_type}]→ {outward}")
        except Exception as e:
            log.exception("jira_link_issues failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    jira_tools = [
        Tool(
            name="jira_search",
            description=(
                "Search Jira issues using JQL (Jira Query Language). "
                "Examples: 'project = PROJ AND status = Open', "
                "'assignee = currentUser() ORDER BY updated DESC', "
                "'text ~ \"login bug\"'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "jql": {"type": "string", "description": "JQL query string."},
                    "limit": {"type": "integer", "description": "Max results (default 20)."},
                },
                "required": ["jql"],
            },
            handler=search_handler,
        ),
        Tool(
            name="jira_get_issue",
            description=(
                "Get full details of a Jira issue by key (e.g. PROJ-123). "
                "Returns summary, status, description, comments, assignee, labels."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Issue key (e.g. PROJ-123)."},
                },
                "required": ["issue_key"],
            },
            handler=get_issue_handler,
        ),
        Tool(
            name="jira_create_issue",
            description="Create a new Jira issue in a project.",
            parameters={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project key (e.g. PROJ)."},
                    "summary": {"type": "string", "description": "Issue title/summary."},
                    "issue_type": {
                        "type": "string",
                        "description": "Issue type (e.g. Task, Bug, Story). Default: Task.",
                    },
                    "description": {"type": "string", "description": "Issue description."},
                },
                "required": ["project", "summary"],
            },
            handler=create_issue_handler,
        ),
        Tool(
            name="jira_update_issue",
            description=(
                "Update fields on an existing Jira issue. Use 'fields' for custom/arbitrary fields "
                "as a JSON object (e.g. story points, sprint). Common custom field examples: "
                '{"customfield_10016": 3} for story points, '
                '{"customfield_10020": {"id": 42}} for sprint.'
            ),
            parameters={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Issue key (e.g. PROJ-123)."},
                    "summary": {"type": "string", "description": "New summary."},
                    "description": {"type": "string", "description": "New description."},
                    "labels": {"type": "string", "description": "Comma-separated labels."},
                    "priority": {"type": "string", "description": "Priority name (e.g. High, Medium, Low)."},
                    "fields": {"type": "string", "description": "JSON object of additional fields to set (custom fields, sprint, story points, etc.)."},
                },
                "required": ["issue_key"],
            },
            handler=update_issue_handler,
        ),
        Tool(
            name="jira_transition",
            description=(
                "Change the status of a Jira issue (e.g. move to 'In Progress', 'Done'). "
                "The status name must match an available transition."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Issue key (e.g. PROJ-123)."},
                    "status": {"type": "string", "description": "Target status name (e.g. 'In Progress', 'Done')."},
                },
                "required": ["issue_key", "status"],
            },
            handler=transition_handler,
        ),
        Tool(
            name="jira_add_comment",
            description="Add a comment to a Jira issue.",
            parameters={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Issue key (e.g. PROJ-123)."},
                    "comment": {"type": "string", "description": "Comment text."},
                },
                "required": ["issue_key", "comment"],
            },
            handler=comment_handler,
        ),
        Tool(
            name="jira_assign",
            description="Assign a Jira issue to a user by account ID.",
            parameters={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Issue key (e.g. PROJ-123)."},
                    "account_id": {"type": "string", "description": "Atlassian account ID of the assignee."},
                },
                "required": ["issue_key", "account_id"],
            },
            handler=assign_handler,
        ),
        Tool(
            name="jira_clone_issue",
            description=(
                "Clone a Jira issue. Copies summary, description, labels, priority, assignee, and issue type. "
                "Creates a link between clone and original. Use 'fields' JSON to override or add fields "
                "(sprint, story points, etc.) on the clone."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Source issue key to clone (e.g. PROJ-123)."},
                    "summary": {"type": "string", "description": "Override summary for the clone. Defaults to original."},
                    "fields": {"type": "string", "description": "JSON object of additional/override fields on the clone."},
                    "link_type": {"type": "string", "description": "Link type name (default: Cloners)."},
                },
                "required": ["issue_key"],
            },
            handler=clone_issue_handler,
        ),
        Tool(
            name="jira_link_issues",
            description=(
                "Create a link between two Jira issues. Common link types: "
                "'Relates', 'Blocks', 'Cloners', 'Duplicate'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "inward_issue": {"type": "string", "description": "Inward issue key (e.g. PROJ-123)."},
                    "outward_issue": {"type": "string", "description": "Outward issue key (e.g. PROJ-456)."},
                    "link_type": {"type": "string", "description": "Link type name (default: Relates)."},
                },
                "required": ["inward_issue", "outward_issue"],
            },
            handler=link_issues_handler,
        ),
    ]

    # --- Confluence handlers ---

    async def conf_search_handler(args: dict[str, Any]) -> ToolResult:
        cql = args.get("cql", "")
        if not cql:
            return ToolResult(content="Error: cql is required", is_error=True)
        limit = args.get("limit", 20)
        try:
            result = await _get_confluence().search(cql, limit=limit)
            results = result.get("results", []) if isinstance(result, dict) else []
            if not results:
                return ToolResult(content="No results found.")
            total = result.get("totalSize", len(results))
            lines = [f"Found {total} result(s), showing {len(results)}:\n"]
            for r in results:
                lines.append(f"- {_format_confluence_result(r)}")
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("confluence_search failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    async def conf_get_page_handler(args: dict[str, Any]) -> ToolResult:
        page_id = args.get("page_id", "")
        space = args.get("space", "")
        title = args.get("title", "")
        if not page_id and not (space and title):
            return ToolResult(content="Error: provide page_id, or both space and title", is_error=True)
        try:
            if page_id:
                page = await _get_confluence().get_page_by_id(page_id)
            else:
                page = await _get_confluence().get_page_by_title(space, title)
            if not page:
                return ToolResult(content="Page not found.")
            return ToolResult(content=_format_confluence_page(page))
        except Exception as e:
            log.exception("confluence_get_page failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    async def conf_create_page_handler(args: dict[str, Any]) -> ToolResult:
        space = args.get("space", "")
        title = args.get("title", "")
        body = args.get("body", "")
        if not space or not title:
            return ToolResult(content="Error: space and title are required", is_error=True)
        parent_id = args.get("parent_id")
        try:
            result = await _get_confluence().create_page(space, title, body, parent_id=parent_id)
            pid = result.get("id", "")
            return ToolResult(content=f"Created page: {title} (id: {pid})")
        except Exception as e:
            log.exception("confluence_create_page failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    async def conf_update_page_handler(args: dict[str, Any]) -> ToolResult:
        page_id = args.get("page_id", "")
        title = args.get("title", "")
        body = args.get("body", "")
        if not page_id or not title:
            return ToolResult(content="Error: page_id and title are required", is_error=True)
        try:
            await _get_confluence().update_page(page_id, title, body)
            return ToolResult(content=f"Updated page: {title} (id: {page_id})")
        except Exception as e:
            log.exception("confluence_update_page failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    async def conf_get_spaces_handler(args: dict[str, Any]) -> ToolResult:
        limit = args.get("limit", 50)
        try:
            spaces = await _get_confluence().get_all_spaces(limit=limit)
            if not spaces:
                return ToolResult(content="No spaces found.")
            lines = [f"Found {len(spaces)} space(s):\n"]
            for s in spaces:
                key = s.get("key", "")
                name = s.get("name", "")
                stype = s.get("type", "")
                lines.append(f"- **{key}** — {name} [{stype}]")
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("confluence_get_spaces failed")
            return ToolResult(content=f"Error: {e}", is_error=True)


    async def conf_render_page_handler(args: dict[str, Any]) -> ToolResult:
        page_id = args.get("page_id", "")
        space = args.get("space", "")
        title = args.get("title", "")
        fmt = args.get("format", "md")
        if fmt not in ("md", "html"):
            return ToolResult(content="Error: format must be 'md' or 'html'", is_error=True)
        if not page_id and not (space and title):
            return ToolResult(content="Error: provide page_id, or both space and title", is_error=True)
        try:
            # Fetch page
            if page_id:
                page = await _get_confluence().get_page_by_id(page_id)
            else:
                page = await _get_confluence().get_page_by_title(space, title)
            if not page:
                return ToolResult(content="Page not found.")

            page_title = page.get("title", "")
            body_storage = page.get("body", {}).get("storage", {}).get("value", "")
            if not body_storage:
                return ToolResult(content=f"# {page_title}\n\n(no content)")

            # Pre-scan for JIRA keys and user IDs to resolve
            refs = extract_refs(body_storage)

            # Build user resolver via Jira API
            user_cache: dict[str, str] = {}
            for account_id in refs.get("user_ids", set()):
                try:
                    user_data = await asyncio.to_thread(
                        _get_jira()._jira.user, account_id=account_id
                    )
                    user_cache[account_id] = user_data.get("displayName", "")
                except Exception:
                    pass

            # Build JIRA resolver via Jira API
            jira_cache: dict[str, tuple[str, str, str]] = {}
            jira_base = _url.rstrip("/")
            for key in refs.get("jira_keys", set()):
                try:
                    issue = await asyncio.to_thread(
                        _get_jira()._jira.get_issue, key, fields="summary,status"
                    )
                    summary = issue.get("fields", {}).get("summary", "")
                    status = issue.get("fields", {}).get("status", {}).get("name", "")
                    url = f"{jira_base}/browse/{key}"
                    jira_cache[key] = (summary, status, url)
                except Exception:
                    pass

            user_resolver = lambda aid: user_cache.get(aid)
            jira_resolver = lambda k: jira_cache.get(k)

            result = confluence_parse(
                body_storage, fmt=fmt, title=page_title,
                jira_base_url=jira_base,
                user_resolver=user_resolver,
                jira_resolver=jira_resolver,
            )
            return ToolResult(content=result)
        except Exception as e:
            log.exception("confluence_render_page failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    confluence_tools = [
        Tool(
            name="confluence_search",
            description=(
                "Search Confluence using CQL (Confluence Query Language). "
                "Examples: 'type = page AND space = PROJ AND text ~ \"deployment\"', "
                "'title = \"Meeting Notes\"', 'label = \"architecture\"'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "cql": {"type": "string", "description": "CQL query string."},
                    "limit": {"type": "integer", "description": "Max results (default 20)."},
                },
                "required": ["cql"],
            },
            handler=conf_search_handler,
        ),
        Tool(
            name="confluence_get_page",
            description=(
                "Get a Confluence page by ID, or by space key + title. "
                "Returns title, space, version, and full body content."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "Page ID (numeric or UUID)."},
                    "space": {"type": "string", "description": "Space key (e.g. PROJ). Used with title."},
                    "title": {"type": "string", "description": "Page title. Used with space."},
                },
            },
            handler=conf_get_page_handler,
        ),
        Tool(
            name="confluence_create_page",
            description="Create a new Confluence page in a space.",
            parameters={
                "type": "object",
                "properties": {
                    "space": {"type": "string", "description": "Space key (e.g. PROJ)."},
                    "title": {"type": "string", "description": "Page title."},
                    "body": {"type": "string", "description": "Page body in Confluence storage format (XHTML)."},
                    "parent_id": {"type": "string", "description": "Optional parent page ID."},
                },
                "required": ["space", "title"],
            },
            handler=conf_create_page_handler,
        ),
        Tool(
            name="confluence_update_page",
            description="Update an existing Confluence page's title and body.",
            parameters={
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "Page ID to update."},
                    "title": {"type": "string", "description": "New page title."},
                    "body": {"type": "string", "description": "New page body in storage format (XHTML)."},
                },
                "required": ["page_id", "title"],
            },
            handler=conf_update_page_handler,
        ),
        Tool(
            name="confluence_get_spaces",
            description="List available Confluence spaces.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max spaces to return (default 50)."},
                },
            },
            handler=conf_get_spaces_handler,
        ),
        Tool(
            name="confluence_render_page",
            description=(
                "Fetch a Confluence page and render it as clean Markdown or HTML. "
                "Automatically resolves JIRA issue references and @user mentions. "
                "Handles macros, tables, code blocks, task lists, panels, emoticons. "
                "Use format='html' for a styled self-contained HTML document."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "Page ID (numeric). Preferred."},
                    "space": {"type": "string", "description": "Space key (e.g. PROJ). Used with title."},
                    "title": {"type": "string", "description": "Page title. Used with space."},
                    "format": {
                        "type": "string",
                        "description": "Output format: 'md' (Markdown, default) or 'html' (styled HTML document).",
                        "enum": ["md", "html"],
                    },
                },
            },
            handler=conf_render_page_handler,
        ),
    ]

    return jira_tools + confluence_tools


def _format_confluence_result(result: dict) -> str:
    """Format a single CQL search result."""
    content = result.get("content", result)
    title = content.get("title", result.get("title", ""))
    cid = content.get("id", result.get("id", ""))
    ctype = content.get("type", result.get("type", ""))
    space = content.get("space", {}).get("key", "") if isinstance(content.get("space"), dict) else ""
    excerpt = result.get("excerpt", "")
    parts = [f"**{title}**"]
    tags = []
    if cid:
        tags.append(f"id:{cid}")
    if space:
        tags.append(space)
    if ctype:
        tags.append(ctype)
    if tags:
        parts.append(f"[{' · '.join(tags)}]")
    if excerpt:
        clean = excerpt.replace("<@hl>", "").replace("</@hl>", "").strip()
        if clean:
            parts.append(clean[:120])
    return " — ".join(parts)


def _format_confluence_page(page: dict) -> str:
    """Format full page details, converting storage format to Markdown."""
    title = page.get("title", "")
    pid = page.get("id", "")
    space = page.get("space", {}).get("key", "") if isinstance(page.get("space"), dict) else ""
    version = page.get("version", {}).get("number", "") if isinstance(page.get("version"), dict) else ""
    body_storage = page.get("body", {}).get("storage", {}).get("value", "")

    header = f"# {title}\n**ID:** {pid} | **Space:** {space} | **Version:** {version}\n"
    if not body_storage:
        return header + "\n(no content)"
    try:
        body_md = confluence_parse(body_storage)
    except Exception:
        body_md = body_storage  # fallback to raw if parser fails
    return header + "\n" + body_md


