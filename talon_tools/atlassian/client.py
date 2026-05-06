"""Jira and Confluence client wrappers using atlassian-python-api."""

from __future__ import annotations

import asyncio
import logging
from functools import partial

from atlassian import Jira, Confluence
from talon_tools.credentials import get as cred

log = logging.getLogger(__name__)


class JiraClient:
    """Thin async wrapper around the sync Jira client."""

    def __init__(self) -> None:
        url = cred("JIRA_URL")
        username = cred("JIRA_USERNAME")
        token = cred("JIRA_API_TOKEN")
        self._jira = Jira(url=url, username=username, password=token, cloud=True)

    async def search(self, jql: str, limit: int = 20) -> dict:
        return await asyncio.to_thread(
            self._jira.jql, jql, fields="summary,status,assignee,priority,issuetype,created,updated", limit=limit
        )

    async def get_issue(self, key: str) -> dict:
        return await asyncio.to_thread(
            self._jira.get_issue, key, fields="summary,status,assignee,priority,issuetype,description,comment,labels,created,updated"
        )

    async def create_issue(self, project: str, summary: str, issue_type: str = "Task", description: str = "") -> dict:
        fields = {
            "project": {"key": project},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }
        if description:
            fields["description"] = description
        return await asyncio.to_thread(self._jira.create_issue, fields)

    async def update_fields(self, key: str, fields: dict) -> None:
        await asyncio.to_thread(self._jira.update_issue_field, key, fields)

    async def transition(self, key: str, status: str) -> None:
        await asyncio.to_thread(self._jira.set_issue_status, key, status)

    async def add_comment(self, key: str, comment: str) -> dict:
        return await asyncio.to_thread(self._jira.issue_add_comment, key, comment)

    async def assign(self, key: str, account_id: str) -> None:
        await asyncio.to_thread(self._jira.assign_issue, key, account_id)

    async def get_transitions(self, key: str) -> list[dict]:
        return await asyncio.to_thread(self._jira.get_issue_transitions, key)

    async def myself(self) -> dict:
        return await asyncio.to_thread(self._jira.myself)


class ConfluenceClient:
    """Thin async wrapper around the sync Confluence client."""

    def __init__(self) -> None:
        url = cred("JIRA_URL")  # same Atlassian Cloud instance
        username = cred("JIRA_USERNAME")
        token = cred("JIRA_API_TOKEN")
        self._confluence = Confluence(url=url, username=username, password=token, cloud=True)

    async def search(self, cql: str, limit: int = 20) -> dict:
        return await asyncio.to_thread(self._confluence.cql, cql, limit=limit)

    async def get_page_by_id(self, page_id: str) -> dict:
        return await asyncio.to_thread(
            self._confluence.get_page_by_id, page_id, expand="body.storage,version,space"
        )

    async def get_page_by_title(self, space: str, title: str) -> dict | None:
        return await asyncio.to_thread(self._confluence.get_page_by_title, space, title)

    async def create_page(self, space: str, title: str, body: str, parent_id: str | None = None) -> dict:
        return await asyncio.to_thread(
            self._confluence.create_page, space, title, body, parent_id=parent_id
        )

    async def update_page(self, page_id: str, title: str, body: str) -> dict:
        return await asyncio.to_thread(
            self._confluence.update_page, page_id, title, body
        )

    async def get_all_spaces(self, limit: int = 50) -> list:
        result = await asyncio.to_thread(self._confluence.get_all_spaces, start=0, limit=limit)
        return result.get("results", []) if isinstance(result, dict) else result
