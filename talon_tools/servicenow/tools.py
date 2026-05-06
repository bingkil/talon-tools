"""ServiceNow direct API tools — my_cases, my_change_requests."""

import asyncio
import base64
import json

import aiohttp

from talon_tools import Tool, ToolResult
from talon_tools.credentials import get as cred


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
