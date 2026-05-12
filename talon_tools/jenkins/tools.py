"""Jenkins tool definitions for Talon agents."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from talon_tools import Tool, ToolResult

from .client import JenkinsClient, available_servers

log = logging.getLogger(__name__)


def _ts_to_str(ms: int | None) -> str:
    """Convert Jenkins millisecond timestamp to human-readable string."""
    if not ms:
        return "unknown"
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _duration_str(ms: int | None) -> str:
    """Format duration in milliseconds to human-readable."""
    if not ms:
        return "unknown"
    secs = ms // 1000
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    secs = secs % 60
    if mins < 60:
        return f"{mins}m {secs}s"
    hours = mins // 60
    mins = mins % 60
    return f"{hours}h {mins}m"


def _color_to_status(color: str) -> str:
    """Convert Jenkins color code to readable status."""
    mapping = {
        "blue": "Success",
        "red": "Failed",
        "yellow": "Unstable",
        "grey": "Not built",
        "disabled": "Disabled",
        "aborted": "Aborted",
        "notbuilt": "Not built",
    }
    base = color.rstrip("_anime") if color else "unknown"
    status = mapping.get(base, color or "unknown")
    if color and color.endswith("_anime"):
        status += " (building)"
    return status


def _format_job(job: dict) -> str:
    """Format a single job for display."""
    name = job.get("name", "")
    color = job.get("color", "")
    status = _color_to_status(color)
    last = job.get("lastBuild")
    if last:
        num = last.get("number", "?")
        result = last.get("result") or ("Building" if last.get("building") else "?")
        return f"**{name}** — {status} (#{num}: {result})"
    return f"**{name}** — {status}"


def _format_build_detail(build: dict, job_name: str) -> str:
    """Format detailed build info."""
    number = build.get("number", "?")
    result = build.get("result") or ("Building..." if build.get("building") else "Pending")
    duration = _duration_str(build.get("duration"))
    estimated = _duration_str(build.get("estimatedDuration"))
    started = _ts_to_str(build.get("timestamp"))

    lines = [
        f"# {job_name} #{number}",
        f"**Result:** {result}",
        f"**Started:** {started}",
        f"**Duration:** {duration} (estimated: {estimated})",
    ]

    # Causes
    for action in build.get("actions", []):
        causes = action.get("causes", [])
        for cause in causes:
            desc = cause.get("shortDescription", "")
            if desc:
                lines.append(f"**Trigger:** {desc}")

    # Changes
    for cs in build.get("changeSets", []):
        items = cs.get("items", [])
        if items:
            lines.append(f"\n**Changes ({len(items)}):**")
            for item in items[:10]:
                author = item.get("author", {}).get("fullName", "?")
                msg = item.get("msg", "").split("\n")[0]
                commit = item.get("commitId", "")[:8]
                lines.append(f"- `{commit}` {msg} ({author})")

    return "\n".join(lines)


def build_tools() -> list[Tool]:
    """Return Jenkins tools for agent use."""

    _clients: dict[str, JenkinsClient] = {}

    def _get_client(server: str | None = None) -> JenkinsClient:
        key = server or "default"
        if key not in _clients:
            _clients[key] = JenkinsClient(server)
        return _clients[key]

    # Helper: build server description suffix for multi-instance awareness
    def _server_desc() -> str:
        servers = available_servers()
        if len(servers) <= 1:
            return ""
        return f" Available servers: {', '.join(servers)}."

    # ------------------------------------------------------------------
    # jenkins_servers — list configured instances
    # ------------------------------------------------------------------
    async def servers_handler(args: dict[str, Any]) -> ToolResult:
        servers = available_servers()
        if not servers:
            return ToolResult(content="No Jenkins servers configured.")
        lines = [f"**Configured Jenkins Servers** ({len(servers)}):\n"]
        for s in servers:
            lines.append(f"- **{s}**")
        return ToolResult(content="\n".join(lines))

    # ------------------------------------------------------------------
    # jenkins_jobs — list jobs
    # ------------------------------------------------------------------
    async def jobs_handler(args: dict[str, Any]) -> ToolResult:
        folder = args.get("folder", "")
        server = args.get("server")
        try:
            client = _get_client(server)
            jobs = await client.get_jobs(folder)
            if not jobs:
                return ToolResult(content="No jobs found.")
            label = f" [{client._server}]" if client._server != "default" else ""
            lines = [f"**Jenkins Jobs{label}** ({len(jobs)}):\n"]
            for job in jobs:
                lines.append(f"- {_format_job(job)}")
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("jenkins_jobs failed")
            return ToolResult(content=f"Error listing jobs: {e}", is_error=True)

    # ------------------------------------------------------------------
    # jenkins_tree — recursive folder walk
    # ------------------------------------------------------------------
    async def tree_handler(args: dict[str, Any]) -> ToolResult:
        folder = args.get("folder", "")
        max_depth = args.get("max_depth", 5)
        server = args.get("server")
        try:
            client = _get_client(server)
            items = await client.list_tree(folder, max_depth=max_depth)
            if not items:
                return ToolResult(content="No jobs or folders found.")
            label = f" [{client._server}]" if client._server != "default" else ""
            lines = [f"**Jenkins Tree{label}** ({sum(1 for i in items if i['type'] == 'job')} jobs, "
                     f"{sum(1 for i in items if i['type'] == 'folder')} folders):\n"]
            for item in items:
                indent = "  " * item["depth"]
                if item["type"] == "folder":
                    lines.append(f"{indent}📁 **{item['name']}/**")
                else:
                    status = _color_to_status(item.get("color", ""))
                    lines.append(f"{indent}  {item['name']} — {status}")
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("jenkins_tree failed")
            return ToolResult(content=f"Error walking tree: {e}", is_error=True)

    # ------------------------------------------------------------------
    # jenkins_status — get job/build status
    # ------------------------------------------------------------------
    async def status_handler(args: dict[str, Any]) -> ToolResult:
        job_name = args.get("job_name", "")
        if not job_name:
            return ToolResult(content="Error: job_name is required.", is_error=True)
        build_number = args.get("build_number")
        server = args.get("server")
        try:
            client = _get_client(server)
            if build_number:
                build = await client.get_build(job_name, build_number)
                return ToolResult(content=_format_build_detail(build, job_name))
            else:
                job = await client.get_job(job_name)
                name = job.get("name", job_name)
                color = job.get("color", "")
                status = _color_to_status(color)
                desc = job.get("description") or ""

                lines = [f"# {name}", f"**Status:** {status}"]
                if desc:
                    lines.append(f"**Description:** {desc}")

                # Health reports
                for h in job.get("healthReport", []):
                    lines.append(f"**Health:** {h.get('description', '')} (score: {h.get('score', '?')})")

                # Last build
                last = job.get("lastBuild")
                if last:
                    num = last.get("number", "?")
                    result = last.get("result") or ("Building" if last.get("building") else "?")
                    duration = _duration_str(last.get("duration"))
                    started = _ts_to_str(last.get("timestamp"))
                    lines.append(f"\n**Last Build:** #{num} — {result}")
                    lines.append(f"  Started: {started} | Duration: {duration}")

                # Last success/failure
                last_ok = job.get("lastSuccessfulBuild")
                last_fail = job.get("lastFailedBuild")
                if last_ok:
                    lines.append(f"**Last Success:** #{last_ok.get('number', '?')} ({_ts_to_str(last_ok.get('timestamp'))})")
                if last_fail:
                    lines.append(f"**Last Failure:** #{last_fail.get('number', '?')} ({_ts_to_str(last_fail.get('timestamp'))})")

                return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("jenkins_status failed")
            return ToolResult(content=f"Error getting status: {e}", is_error=True)

    # ------------------------------------------------------------------
    # jenkins_logs — get console output
    # ------------------------------------------------------------------
    async def logs_handler(args: dict[str, Any]) -> ToolResult:
        job_name = args.get("job_name", "")
        if not job_name:
            return ToolResult(content="Error: job_name is required.", is_error=True)
        build_number = args.get("build_number", "lastBuild")
        tail = args.get("tail", 100)
        server = args.get("server")
        try:
            output = await _get_client(server).get_console(job_name, build_number, tail=tail)
            return ToolResult(content=f"**Console output for {job_name} #{build_number}:**\n\n```\n{output}\n```")
        except Exception as e:
            log.exception("jenkins_logs failed")
            return ToolResult(content=f"Error getting logs: {e}", is_error=True)

    # ------------------------------------------------------------------
    # jenkins_build — trigger a build
    # ------------------------------------------------------------------
    async def build_handler(args: dict[str, Any]) -> ToolResult:
        job_name = args.get("job_name", "")
        if not job_name:
            return ToolResult(content="Error: job_name is required.", is_error=True)
        parameters = args.get("parameters")
        server = args.get("server")
        try:
            location = await _get_client(server).trigger_build(job_name, parameters)
            return ToolResult(content=f"Build triggered for **{job_name}**.\nQueue: {location}")
        except Exception as e:
            log.exception("jenkins_build failed")
            return ToolResult(content=f"Error triggering build: {e}", is_error=True)

    # ------------------------------------------------------------------
    # jenkins_queue — view build queue
    # ------------------------------------------------------------------
    async def queue_handler(args: dict[str, Any]) -> ToolResult:
        server = args.get("server")
        try:
            items = await _get_client(server).get_queue()
            if not items:
                return ToolResult(content="Build queue is empty.")
            lines = [f"**Build Queue** ({len(items)} items):\n"]
            for item in items:
                task = item.get("task", {})
                name = task.get("name", "?")
                why = item.get("why", "")
                lines.append(f"- **{name}** — {why}")
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("jenkins_queue failed")
            return ToolResult(content=f"Error getting queue: {e}", is_error=True)

    # ------------------------------------------------------------------
    # jenkins_nodes — executor status
    # ------------------------------------------------------------------
    async def nodes_handler(args: dict[str, Any]) -> ToolResult:
        server = args.get("server")
        try:
            nodes = await _get_client(server).get_nodes()
            if not nodes:
                return ToolResult(content="No nodes found.")
            lines = [f"**Jenkins Nodes** ({len(nodes)}):\n"]
            for node in nodes:
                name = node.get("displayName", "?")
                offline = node.get("offline", False)
                executors = node.get("numExecutors", 0)
                idle = node.get("idle", False)
                status = "Offline" if offline else ("Idle" if idle else "Busy")
                lines.append(f"- **{name}** — {status} ({executors} executors)")
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("jenkins_nodes failed")
            return ToolResult(content=f"Error getting nodes: {e}", is_error=True)

    # ------------------------------------------------------------------
    # jenkins_stop — abort a running build
    # ------------------------------------------------------------------
    async def stop_handler(args: dict[str, Any]) -> ToolResult:
        job_name = args.get("job_name", "")
        if not job_name:
            return ToolResult(content="Error: job_name is required.", is_error=True)
        build_number = args.get("build_number", "lastBuild")
        server = args.get("server")
        try:
            await _get_client(server).stop_build(job_name, build_number)
            return ToolResult(content=f"Stop signal sent to **{job_name}** #{build_number}.")
        except Exception as e:
            log.exception("jenkins_stop failed")
            return ToolResult(content=f"Error stopping build: {e}", is_error=True)

    # Build the server property description dynamically
    server_prop = {
        "type": "string",
        "description": f"Jenkins server alias (omit for default).{_server_desc()}",
    }

    return [
        Tool(
            name="jenkins_servers",
            description="List configured Jenkins server instances.",
            parameters={"type": "object", "properties": {}},
            handler=servers_handler,
        ),
        Tool(
            name="jenkins_jobs",
            description="List Jenkins jobs and their current status. Optionally filter by folder.",
            parameters={
                "type": "object",
                "properties": {
                    "folder": {
                        "type": "string",
                        "description": "Folder path to list jobs from (empty for top-level).",
                    },
                    "server": server_prop,
                },
            },
            handler=jobs_handler,
        ),
        Tool(
            name="jenkins_tree",
            description="Recursively walk Jenkins folder structure. Shows all folders and jobs as a tree.",
            parameters={
                "type": "object",
                "properties": {
                    "folder": {
                        "type": "string",
                        "description": "Starting folder (empty for root).",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum folder depth to traverse. Default: 5.",
                    },
                    "server": server_prop,
                },
            },
            handler=tree_handler,
        ),
        Tool(
            name="jenkins_status",
            description="Get status of a Jenkins job or specific build. Shows last build result, health, and history.",
            parameters={
                "type": "object",
                "properties": {
                    "job_name": {
                        "type": "string",
                        "description": "Name of the Jenkins job (use folder/job for nested jobs).",
                    },
                    "build_number": {
                        "type": "integer",
                        "description": "Specific build number. Omit for latest build info.",
                    },
                    "server": server_prop,
                },
                "required": ["job_name"],
            },
            handler=status_handler,
        ),
        Tool(
            name="jenkins_logs",
            description="Get console output (logs) from a Jenkins build. Useful for diagnosing failures.",
            parameters={
                "type": "object",
                "properties": {
                    "job_name": {
                        "type": "string",
                        "description": "Name of the Jenkins job.",
                    },
                    "build_number": {
                        "type": "integer",
                        "description": "Build number. Omit for latest build.",
                    },
                    "tail": {
                        "type": "integer",
                        "description": "Number of lines to return from the end. Default: 100.",
                    },
                    "server": server_prop,
                },
                "required": ["job_name"],
            },
            handler=logs_handler,
        ),
        Tool(
            name="jenkins_build",
            description="Trigger a Jenkins build. Optionally pass parameters for parameterized jobs.",
            parameters={
                "type": "object",
                "properties": {
                    "job_name": {
                        "type": "string",
                        "description": "Name of the Jenkins job to build.",
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Build parameters as key-value pairs (for parameterized jobs).",
                    },
                    "server": server_prop,
                },
                "required": ["job_name"],
            },
            handler=build_handler,
        ),
        Tool(
            name="jenkins_queue",
            description="View the Jenkins build queue — shows what's waiting to be built and why.",
            parameters={
                "type": "object",
                "properties": {
                    "server": server_prop,
                },
            },
            handler=queue_handler,
        ),
        Tool(
            name="jenkins_nodes",
            description="Get Jenkins node/executor status — shows which agents are online, busy, or idle.",
            parameters={
                "type": "object",
                "properties": {
                    "server": server_prop,
                },
            },
            handler=nodes_handler,
        ),
        Tool(
            name="jenkins_stop",
            description="Stop/abort a running Jenkins build.",
            parameters={
                "type": "object",
                "properties": {
                    "job_name": {
                        "type": "string",
                        "description": "Name of the Jenkins job.",
                    },
                    "build_number": {
                        "type": "integer",
                        "description": "Build number to stop. Omit for latest build.",
                    },
                    "server": server_prop,
                },
                "required": ["job_name"],
            },
            handler=stop_handler,
        ),
    ]
