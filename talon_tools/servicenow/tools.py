"""ServiceNow direct API tools.

Personal tools: my_cases, my_change_requests
Extended tools: incidents, incident details, change details, knowledge,
                catalog, users, agile stories
"""

import asyncio
import base64
import json
import logging

import aiohttp

from talon_tools import Tool, ToolResult
from talon_tools.credentials import get as cred

log = logging.getLogger(__name__)


def _dv(record: dict, key: str) -> str:
    """Extract display value from a field (may be dict or string)."""
    val = record.get(key, "")
    if isinstance(val, dict):
        return val.get("display_value", "") or val.get("value", "")
    return str(val) if val else ""


async def _query(table: str, query: str, limit: int = 20) -> list[dict]:
    url = cred("SERVICENOW_URL")
    user = cred("SERVICENOW_USERNAME")
    passwd = cred("SERVICENOW_PASSWORD")
    auth = base64.b64encode(f"{user}:{passwd}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Accept": "application/json"}
    params = {
        "sysparm_query": query,
        "sysparm_limit": str(limit),
        "sysparm_display_value": "true",
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{url}/api/now/table/{table}", params=params) as r:
            data = await r.json()
            return data.get("result", [])


async def _my_cases(args: dict) -> ToolResult:
    status = (args.get("status") or "open").lower()
    limit = int(args.get("limit") or 20)

    parts = [f"opened_by.user_name={cred('SERVICENOW_USERNAME')}"]
    if status == "open":
        parts.append("stateNOT IN6,7,8,3")  # exclude Closed, Cancelled, Resolved
    elif status == "closed":
        parts.append("stateIN6,7,8,3")
    parts.append("ORDERBYDESCsys_created_on")

    records = await _query("sn_customerservice_case", "^".join(parts), limit)
    cases = [
        {
            "number": r.get("number", ""),
            "state": _dv(r, "state"),
            "short_description": r.get("short_description", ""),
            "priority": _dv(r, "priority"),
            "opened_at": r.get("opened_at", ""),
        }
        for r in records
    ]
    return ToolResult(json.dumps({"count": len(cases), "cases": cases}))


async def _my_change_requests(args: dict) -> ToolResult:
    status = (args.get("status") or "open").lower()
    limit = int(args.get("limit") or 20)

    parts = [f"requested_by.user_name={cred('SERVICENOW_USERNAME')}"]
    if status == "open":
        parts.append("stateNOT IN3,4,7")  # exclude Closed, Complete, Cancelled
    elif status == "closed":
        parts.append("stateIN3,4,7")
    parts.append("ORDERBYDESCsys_created_on")

    records = await _query("change_request", "^".join(parts), limit)
    crs = [
        {
            "number": r.get("number", ""),
            "state": _dv(r, "state"),
            "short_description": r.get("short_description", ""),
            "priority": _dv(r, "priority"),
            "risk": _dv(r, "risk"),
            "assigned_to": _dv(r, "assigned_to"),
            "start_date": r.get("start_date", ""),
            "end_date": r.get("end_date", ""),
        }
        for r in records
    ]
    return ToolResult(json.dumps({"count": len(crs), "change_requests": crs}))


def build_tools() -> list[Tool]:
    return [
        Tool(
            name="my_cases",
            description="List my ServiceNow cases (CSxxxxxx). Filter by status: open (default) or closed.",
            parameters={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["open", "closed"], "description": "Filter: open or closed"},
                    "limit": {"type": "integer", "description": "Max results (default 20)"},
                },
            },
            handler=_my_cases,
        ),
        Tool(
            name="my_change_requests",
            description="List my ServiceNow change requests (CHGxxxxxxx). Filter by status: open (default) or closed.",
            parameters={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["open", "closed"], "description": "Filter: open or closed"},
                    "limit": {"type": "integer", "description": "Max results (default 20)"},
                },
            },
            handler=_my_change_requests,
        ),
    ]


# ===========================================================================
# Extended ServiceNow tools — broader read-only access
# ===========================================================================


async def _list_incidents(args: dict) -> ToolResult:
    query = args.get("query", "")
    state = args.get("state", "")
    priority = args.get("priority", "")
    assigned_to = args.get("assigned_to", "")
    limit = int(args.get("limit") or 20)

    parts = []
    if query:
        parts.append(f"short_descriptionLIKE{query}")
    if state:
        parts.append(f"state={state}")
    if priority:
        parts.append(f"priority={priority}")
    if assigned_to:
        parts.append(f"assigned_to.user_name={assigned_to}")
    parts.append("ORDERBYDESCsys_created_on")

    records = await _query("incident", "^".join(parts), limit)
    incidents = [
        {
            "number": r.get("number", ""),
            "state": _dv(r, "state"),
            "short_description": r.get("short_description", ""),
            "priority": _dv(r, "priority"),
            "assigned_to": _dv(r, "assigned_to"),
            "assignment_group": _dv(r, "assignment_group"),
            "opened_at": r.get("opened_at", ""),
        }
        for r in records
    ]
    return ToolResult(json.dumps({"count": len(incidents), "incidents": incidents}))


async def _get_incident(args: dict) -> ToolResult:
    number = args.get("number", "")
    if not number:
        return ToolResult(content="Error: number is required.", is_error=True)
    records = await _query("incident", f"number={number}", 1)
    if not records:
        return ToolResult(content=f"Incident {number} not found.", is_error=True)
    r = records[0]
    incident = {
        "number": r.get("number", ""),
        "state": _dv(r, "state"),
        "short_description": r.get("short_description", ""),
        "description": r.get("description", ""),
        "priority": _dv(r, "priority"),
        "impact": _dv(r, "impact"),
        "urgency": _dv(r, "urgency"),
        "assigned_to": _dv(r, "assigned_to"),
        "assignment_group": _dv(r, "assignment_group"),
        "category": r.get("category", ""),
        "opened_at": r.get("opened_at", ""),
        "updated_on": r.get("sys_updated_on", ""),
        "resolved_at": r.get("resolved_at", ""),
        "close_notes": r.get("close_notes", ""),
    }
    return ToolResult(json.dumps(incident))


async def _get_change_details(args: dict) -> ToolResult:
    number = args.get("number", "")
    if not number:
        return ToolResult(content="Error: number is required.", is_error=True)
    records = await _query("change_request", f"number={number}", 1)
    if not records:
        return ToolResult(content=f"Change request {number} not found.", is_error=True)
    r = records[0]
    change = {
        "number": r.get("number", ""),
        "state": _dv(r, "state"),
        "type": r.get("type", ""),
        "short_description": r.get("short_description", ""),
        "description": r.get("description", ""),
        "priority": _dv(r, "priority"),
        "risk": _dv(r, "risk"),
        "impact": _dv(r, "impact"),
        "assigned_to": _dv(r, "assigned_to"),
        "assignment_group": _dv(r, "assignment_group"),
        "start_date": r.get("start_date", ""),
        "end_date": r.get("end_date", ""),
    }
    # Get associated tasks
    tasks_records = await _query("change_task", f"change_request.number={number}", 50)
    tasks = [
        {
            "number": t.get("number", ""),
            "short_description": t.get("short_description", ""),
            "state": _dv(t, "state"),
            "assigned_to": _dv(t, "assigned_to"),
        }
        for t in tasks_records
    ]
    change["tasks"] = tasks
    return ToolResult(json.dumps(change))


async def _search_knowledge(args: dict) -> ToolResult:
    query = args.get("query", "")
    if not query:
        return ToolResult(content="Error: query is required.", is_error=True)
    limit = int(args.get("limit") or 10)
    parts = [
        "workflow_state=published",
        f"short_descriptionLIKE{query}^ORtextLIKE{query}",
        "ORDERBYDESCsys_view_count",
    ]
    records = await _query("kb_knowledge", "^".join(parts), limit)
    articles = [
        {
            "number": r.get("number", ""),
            "title": r.get("short_description", ""),
            "category": _dv(r, "kb_category"),
            "views": r.get("sys_view_count", "0"),
        }
        for r in records
    ]
    return ToolResult(json.dumps({"count": len(articles), "articles": articles}))


async def _get_article(args: dict) -> ToolResult:
    number = args.get("number", "")
    if not number:
        return ToolResult(content="Error: number is required (e.g. KB0012345).", is_error=True)
    records = await _query("kb_knowledge", f"number={number}", 1)
    if not records:
        return ToolResult(content=f"Article {number} not found.", is_error=True)
    r = records[0]
    # Strip HTML from text field
    text = r.get("text", "")
    try:
        from bs4 import BeautifulSoup
        text = BeautifulSoup(text, "html.parser").get_text(separator="\n", strip=True)
    except ImportError:
        pass  # Return raw text if bs4 not available
    article = {
        "number": r.get("number", ""),
        "title": r.get("short_description", ""),
        "text": text[:5000],  # Truncate very long articles
        "category": _dv(r, "kb_category"),
        "workflow_state": r.get("workflow_state", ""),
    }
    return ToolResult(json.dumps(article))


async def _list_catalog_items(args: dict) -> ToolResult:
    category = args.get("category", "")
    limit = int(args.get("limit") or 20)
    parts = ["active=true"]
    if category:
        parts.append(f"categoryLIKE{category}")
    records = await _query("sc_cat_item", "^".join(parts), limit)
    items = [
        {
            "sys_id": r.get("sys_id", ""),
            "name": r.get("name", ""),
            "short_description": r.get("short_description", ""),
            "category": _dv(r, "category"),
            "price": r.get("price", "0"),
        }
        for r in records
    ]
    return ToolResult(json.dumps({"count": len(items), "items": items}))


async def _list_users(args: dict) -> ToolResult:
    query = args.get("query", "")
    limit = int(args.get("limit") or 20)
    parts = ["active=true"]
    if query:
        parts.append(f"nameLIKE{query}^ORuser_nameLIKE{query}^ORemailLIKE{query}")
    records = await _query("sys_user", "^".join(parts), limit)
    users = [
        {
            "user_name": r.get("user_name", ""),
            "name": r.get("name", ""),
            "email": r.get("email", ""),
            "department": _dv(r, "department"),
            "title": r.get("title", ""),
        }
        for r in records
    ]
    return ToolResult(json.dumps({"count": len(users), "users": users}))


async def _list_stories(args: dict) -> ToolResult:
    sprint = args.get("sprint", "")
    state = args.get("state", "")
    limit = int(args.get("limit") or 20)
    parts = []
    if sprint:
        parts.append(f"sprint.short_descriptionLIKE{sprint}")
    if state:
        parts.append(f"state={state}")
    parts.append("ORDERBYDESCsys_created_on")
    try:
        records = await _query("rm_story", "^".join(parts), limit)
    except Exception:
        return ToolResult(json.dumps({"count": 0, "stories": [], "note": "Agile module may not be installed."}))
    stories = [
        {
            "number": r.get("number", ""),
            "short_description": r.get("short_description", ""),
            "state": _dv(r, "state"),
            "priority": _dv(r, "priority"),
            "story_points": r.get("story_points", ""),
            "sprint": _dv(r, "sprint"),
            "assigned_to": _dv(r, "assigned_to"),
        }
        for r in records
    ]
    return ToolResult(json.dumps({"count": len(stories), "stories": stories}))


def build_extended_tools() -> list[Tool]:
    """Return extended ServiceNow tools (broader read-only access)."""
    return [
        Tool(
            name="servicenow_incidents",
            description="List ServiceNow incidents. Filter by query, state, priority, or assignee.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search in short description."},
                    "state": {"type": "string", "description": "State filter (e.g. 1=New, 2=In Progress, 6=Resolved, 7=Closed)."},
                    "priority": {"type": "string", "description": "Priority filter (1=Critical, 2=High, 3=Moderate, 4=Low)."},
                    "assigned_to": {"type": "string", "description": "Username of assignee."},
                    "limit": {"type": "integer", "description": "Max results (default 20)."},
                },
            },
            handler=_list_incidents,
        ),
        Tool(
            name="servicenow_incident",
            description="Get detailed information about a specific ServiceNow incident by number (e.g. INC0012345).",
            parameters={
                "type": "object",
                "properties": {
                    "number": {"type": "string", "description": "Incident number (e.g. INC0012345)."},
                },
                "required": ["number"],
            },
            handler=_get_incident,
        ),
        Tool(
            name="servicenow_change_details",
            description="Get detailed information about a change request including associated tasks.",
            parameters={
                "type": "object",
                "properties": {
                    "number": {"type": "string", "description": "Change request number (e.g. CHG0012345)."},
                },
                "required": ["number"],
            },
            handler=_get_change_details,
        ),
        Tool(
            name="servicenow_knowledge",
            description="Search ServiceNow Knowledge Base articles.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search text (searches title and body)."},
                    "limit": {"type": "integer", "description": "Max results (default 10)."},
                },
                "required": ["query"],
            },
            handler=_search_knowledge,
        ),
        Tool(
            name="servicenow_article",
            description="Get full content of a ServiceNow Knowledge Base article by number.",
            parameters={
                "type": "object",
                "properties": {
                    "number": {"type": "string", "description": "Article number (e.g. KB0012345)."},
                },
                "required": ["number"],
            },
            handler=_get_article,
        ),
        Tool(
            name="servicenow_catalog",
            description="Browse ServiceNow Service Catalog items. Optionally filter by category.",
            parameters={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Category filter (partial match)."},
                    "limit": {"type": "integer", "description": "Max results (default 20)."},
                },
            },
            handler=_list_catalog_items,
        ),
        Tool(
            name="servicenow_users",
            description="Search ServiceNow users by name, username, or email.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search text (name, username, or email)."},
                    "limit": {"type": "integer", "description": "Max results (default 20)."},
                },
            },
            handler=_list_users,
        ),
        Tool(
            name="servicenow_stories",
            description="List agile user stories from ServiceNow. Filter by sprint or state.",
            parameters={
                "type": "object",
                "properties": {
                    "sprint": {"type": "string", "description": "Sprint name filter (partial match)."},
                    "state": {"type": "string", "description": "State filter."},
                    "limit": {"type": "integer", "description": "Max results (default 20)."},
                },
            },
            handler=_list_stories,
        ),
    ]
