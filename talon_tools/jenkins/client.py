"""Jenkins REST API client.

Supports multiple Jenkins instances via named servers.  Credentials are
looked up as ``JENKINS_<SERVER>_URL`` / ``_USERNAME`` / ``_TOKEN`` where
``<SERVER>`` is the uppercase server alias.  A bare ``JENKINS_URL`` (no
alias) is treated as the ``default`` server for backward compatibility.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from urllib.parse import quote as urlquote

import httpx
from talon_tools.credentials import get as cred

log = logging.getLogger(__name__)

# Maximum folder depth when walking the tree (safety net).
_MAX_WALK_DEPTH = 10


def _resolve_creds(server: str | None = None) -> tuple[str, str, str]:
    """Return (url, username, token) for *server*, falling back to default."""
    if server and server != "default":
        prefix = f"JENKINS_{server.upper()}"
        url = cred(f"{prefix}_URL", "")
        username = cred(f"{prefix}_USERNAME", "")
        token = cred(f"{prefix}_TOKEN", "")
        if url and username and token:
            return url, username, token
        # Fall through to default if the named server isn't fully configured.

    # Default (no prefix, or prefix lookup failed)
    url = cred("JENKINS_URL", "")
    username = cred("JENKINS_USERNAME", "")
    token = cred("JENKINS_TOKEN", "")
    if not url or not username or not token:
        hint = f" (server={server})" if server else ""
        raise RuntimeError(
            f"Jenkins credentials not configured{hint}. "
            "Set JENKINS_URL, JENKINS_USERNAME, and JENKINS_TOKEN "
            "(or JENKINS_<SERVER>_URL etc. for named instances)."
        )
    return url, username, token


def available_servers() -> list[str]:
    """Return a list of configured Jenkins server aliases.

    Scans credential store and env vars for ``JENKINS_<NAME>_URL`` keys.
    Always includes ``"default"`` if the bare ``JENKINS_URL`` is set.
    """
    import os
    from talon_tools.credentials import _store as cred_store

    servers: list[str] = []
    if cred("JENKINS_URL", ""):
        servers.append("default")

    # Merge keys from file store + env vars
    all_keys = set(k.upper() for k in cred_store)
    all_keys.update(k.upper() for k in os.environ)

    for key in sorted(all_keys):
        if key.startswith("JENKINS_") and key.endswith("_URL") and key != "JENKINS_URL":
            name = key.removeprefix("JENKINS_").removesuffix("_URL").lower()
            if name not in servers:
                servers.append(name)
    return servers


class JenkinsClient:
    """Async wrapper around Jenkins REST API using httpx.

    Args:
        server: Named server alias (e.g. ``"prod"``, ``"staging"``).
                ``None`` or ``"default"`` uses bare ``JENKINS_*`` creds.
    """

    def __init__(self, server: str | None = None) -> None:
        url, username, token = _resolve_creds(server)
        self._server = server or "default"
        self._base = url.rstrip("/")
        self._auth = (username, token)
        self._crumb: dict[str, str] | None = None

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base,
            auth=self._auth,
            timeout=30.0,
            follow_redirects=True,
        )

    async def _get_crumb(self, client: httpx.AsyncClient) -> dict[str, str]:
        """Fetch CSRF crumb token (required for POST requests)."""
        if self._crumb is not None:
            return self._crumb
        try:
            r = await client.get("/crumbIssuer/api/json")
            r.raise_for_status()
            data = r.json()
            self._crumb = {data["crumbRequestField"]: data["crumb"]}
        except (httpx.HTTPStatusError, KeyError):
            # CSRF protection may be disabled
            self._crumb = {}
        return self._crumb

    def _job_path(self, name: str) -> str:
        """Build URL path for a job, handling folder paths like 'folder/job'."""
        parts = name.split("/")
        segments = "/".join(f"job/{urlquote(p, safe='')}" for p in parts)
        return f"/{segments}"

    async def get_jobs(self, folder: str = "") -> list[dict]:
        """List jobs at top level or within a folder."""
        async with self._client() as client:
            path = self._job_path(folder) if folder else ""
            r = await client.get(
                f"{path}/api/json",
                params={"tree": "jobs[name,url,color,lastBuild[number,result,timestamp,building]]"},
            )
            r.raise_for_status()
            return r.json().get("jobs", [])

    async def get_job(self, name: str) -> dict:
        """Get detailed info for a single job."""
        async with self._client() as client:
            r = await client.get(
                f"{self._job_path(name)}/api/json",
                params={
                    "tree": (
                        "name,url,color,buildable,inQueue,description,"
                        "lastBuild[number,result,timestamp,building,duration,estimatedDuration],"
                        "lastSuccessfulBuild[number,timestamp],"
                        "lastFailedBuild[number,timestamp],"
                        "healthReport[description,score]"
                    )
                },
            )
            r.raise_for_status()
            return r.json()

    async def get_build(self, name: str, number: int | str = "lastBuild") -> dict:
        """Get info for a specific build."""
        async with self._client() as client:
            r = await client.get(
                f"{self._job_path(name)}/{number}/api/json",
                params={
                    "tree": (
                        "number,result,building,timestamp,duration,estimatedDuration,"
                        "displayName,description,url,"
                        "actions[causes[shortDescription]],"
                        "changeSets[items[commitId,msg,author[fullName]]]"
                    )
                },
            )
            r.raise_for_status()
            return r.json()

    async def get_console(self, name: str, number: int | str = "lastBuild", tail: int = 200) -> str:
        """Get console output for a build. Returns last `tail` lines."""
        async with self._client() as client:
            r = await client.get(f"{self._job_path(name)}/{number}/consoleText")
            r.raise_for_status()
            lines = r.text.splitlines()
            if len(lines) > tail:
                return f"... ({len(lines) - tail} lines truncated) ...\n" + "\n".join(lines[-tail:])
            return r.text

    async def trigger_build(self, name: str, parameters: dict | None = None) -> str:
        """Trigger a build. Returns queue item URL."""
        async with self._client() as client:
            crumb = await self._get_crumb(client)
            if parameters:
                endpoint = f"{self._job_path(name)}/buildWithParameters"
                r = await client.post(endpoint, headers=crumb, params=parameters)
            else:
                endpoint = f"{self._job_path(name)}/build"
                r = await client.post(endpoint, headers=crumb)
            r.raise_for_status()
            return r.headers.get("Location", "Build queued (no location header)")

    async def get_queue(self) -> list[dict]:
        """Get the current build queue."""
        async with self._client() as client:
            r = await client.get(
                "/queue/api/json",
                params={"tree": "items[id,task[name,url],why,inQueueSince,buildableStartMilliseconds]"},
            )
            r.raise_for_status()
            return r.json().get("items", [])

    async def get_nodes(self) -> list[dict]:
        """Get executor/node status."""
        async with self._client() as client:
            r = await client.get(
                "/computer/api/json",
                params={
                    "tree": (
                        "computer[displayName,offline,temporarilyOffline,"
                        "numExecutors,idle,monitorData[*]]"
                    )
                },
            )
            r.raise_for_status()
            return r.json().get("computer", [])

    async def stop_build(self, name: str, number: int | str = "lastBuild") -> None:
        """Stop/abort a running build."""
        async with self._client() as client:
            crumb = await self._get_crumb(client)
            r = await client.post(
                f"{self._job_path(name)}/{number}/stop",
                headers=crumb,
            )
            r.raise_for_status()

    # ------------------------------------------------------------------
    # Tree walking
    # ------------------------------------------------------------------

    async def walk_jobs(
        self,
        folder: str = "",
        depth: int = 0,
        max_depth: int = _MAX_WALK_DEPTH,
    ) -> list[dict]:
        """Recursively walk folders and return a flat list of all jobs.

        Each returned dict has an extra ``"fullPath"`` key with the
        slash-separated path from root (e.g. ``"team/backend/my-job"``).
        Folders (``_class`` containing ``Folder``) are descended into
        but NOT included in the output.
        """
        if depth > max_depth:
            return []

        items = await self.get_jobs(folder)
        result: list[dict] = []
        for item in items:
            cls = item.get("_class", "")
            name = item.get("name", "")
            path = f"{folder}/{name}" if folder else name

            if "Folder" in cls or "OrganizationFolder" in cls:
                # Recurse into folder
                children = await self.walk_jobs(path, depth + 1, max_depth)
                result.extend(children)
            else:
                item["fullPath"] = path
                result.append(item)
        return result

    async def list_tree(
        self,
        folder: str = "",
        depth: int = 0,
        max_depth: int = _MAX_WALK_DEPTH,
    ) -> list[dict]:
        """Return a tree structure: folders + jobs with nesting info.

        Each item gets ``"fullPath"``, ``"depth"``, and ``"type"``
        (``"folder"`` or ``"job"``).
        """
        if depth > max_depth:
            return []

        items = await self.get_jobs(folder)
        result: list[dict] = []
        for item in items:
            cls = item.get("_class", "")
            name = item.get("name", "")
            path = f"{folder}/{name}" if folder else name

            if "Folder" in cls or "OrganizationFolder" in cls:
                result.append({
                    "name": name,
                    "fullPath": path,
                    "depth": depth,
                    "type": "folder",
                })
                children = await self.list_tree(path, depth + 1, max_depth)
                result.extend(children)
            else:
                result.append({
                    **item,
                    "fullPath": path,
                    "depth": depth,
                    "type": "job",
                })
        return result
