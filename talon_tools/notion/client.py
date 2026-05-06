"""Notion API client wrapper using notion-client AsyncClient."""

from __future__ import annotations

import logging

from notion_client import AsyncClient
from talon_tools.credentials import get as cred

log = logging.getLogger(__name__)

# Notion API version that supports markdown endpoints
NOTION_VERSION = "2022-06-28"


class NotionClient:
    """Thin async wrapper around the Notion SDK."""

    def __init__(self) -> None:
        self._client = AsyncClient(auth=cred("NOTION_TOKEN"))

    async def search(self, query: str, filter_type: str | None = None) -> list[dict]:
        """Search pages and databases by title."""
        kwargs: dict = {"query": query, "page_size": 20}
        if filter_type in ("page", "database"):
            kwargs["filter"] = {"property": "object", "value": filter_type}
        resp = await self._client.search(**kwargs)
        return resp.get("results", [])

    async def read_page_markdown(self, page_id: str) -> dict:
        """Read a page's content as markdown (API version 2026-03-11+)."""
        # The notion-client SDK may not have the markdown method yet,
        # so we use the raw request method.
        resp = await self._client.request(
            path=f"pages/{page_id}/markdown",
            method="GET",
        )
        return resp

    async def create_page(
        self,
        parent_id: str,
        markdown: str,
        title: str | None = None,
        parent_type: str = "page",
    ) -> dict:
        """Create a page with markdown content."""
        parent = (
            {"page_id": parent_id}
            if parent_type == "page"
            else {"database_id": parent_id}
        )
        body: dict = {"parent": parent, "markdown": markdown}
        if title:
            body["properties"] = {"title": [{"text": {"content": title}}]}
        return await self._client.pages.create(**body)

    async def update_page_markdown(
        self, page_id: str, old_str: str, new_str: str
    ) -> dict:
        """Update page content using search-and-replace."""
        return await self._client.request(
            path=f"pages/{page_id}/markdown",
            method="PATCH",
            body={
                "type": "update_content",
                "update_content": {
                    "content_updates": [{"old_str": old_str, "new_str": new_str}]
                },
            },
        )

    async def replace_page_content(self, page_id: str, markdown: str) -> dict:
        """Replace entire page content with new markdown."""
        return await self._client.request(
            path=f"pages/{page_id}/markdown",
            method="PATCH",
            body={
                "type": "replace_content",
                "replace_content": {"new_str": markdown},
            },
        )

    async def query_database(
        self,
        database_id: str,
        filter: dict | None = None,
        sorts: list[dict] | None = None,
    ) -> list[dict]:
        """Query a database with optional filter and sorts."""
        body: dict = {"page_size": 50}
        if filter:
            body["filter"] = filter
        if sorts:
            body["sorts"] = sorts
        # Try data_sources endpoint first, then classic databases endpoint
        for path in [
            f"data_sources/{database_id}/query",
            f"databases/{database_id}/query",
        ]:
            try:
                resp = await self._client.request(
                    path=path, method="POST", body=body,
                )
                return resp.get("results", [])
            except Exception:
                continue
        raise RuntimeError(
            f"Could not query database {database_id}. "
            "Make sure it is shared with your integration."
        )

    async def get_database(self, database_id: str) -> dict:
        """Retrieve database metadata (title, properties/schema)."""
        try:
            return await self._client.databases.retrieve(database_id=database_id)
        except Exception:
            return await self._client.request(
                path=f"data_sources/{database_id}",
                method="GET",
            )
