"""Jenkins tool definitions for Talon agents."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from talon_tools import Tool, ToolResult
from talon_tools.credentials import CredentialRequirement, validate

from .client import JenkinsClient, available_servers

log = logging.getLogger(__name__)

CREDENTIALS = [
    CredentialRequirement("JENKINS_URL", "Jenkins server URL"),
    CredentialRequirement("JENKINS_USERNAME", "Jenkins username"),
    CredentialRequirement("JENKINS_TOKEN", "Jenkins API token", hint="Generate at <your-jenkins>/user/<you>/configure → API Token"),
]


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
    validate("jenkins", CREDENTIALS)

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
    # jenkins_my_builds — find builds triggered by the current user
    # ------------------------------------------------------------------
    async def my_builds_handler(args: dict[str, Any]) -> ToolResult:
        folder = args.get("folder", "")
        limit = int(args.get("limit") or 20)
        server = args.get("server")
        try:
            client = _get_client(server)
            user_id = await client.get_my_user_id()
            if not user_id:
                return ToolResult(content="Error: could not determine current user.", is_error=True)

            # Single API call per folder level — get jobs + builds + causes
            all_builds = await client.get_folder_builds_with_causes(folder, limit_per_job=3)
            my_builds = [b for b in all_builds if b["userId"] == user_id]
            # Sort by timestamp descending
            my_builds.sort(key=lambda b: b.get("timestamp") or 0, reverse=True)

            if not my_builds:
                scope = f" in `{folder}`" if folder else ""
                return ToolResult(content=f"No recent builds triggered by you{scope}. Try a deeper folder path.")

            lines = [f"**My Builds** ({len(my_builds)} found):\n"]
            for b in my_builds[:limit]:
                ts = _ts_to_str(b["timestamp"])
                dur = _duration_str(b["duration"])
                lines.append(f"- **{b['job']}** #{b['number']} — {b['result']} ({ts}, {dur})")
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("jenkins_my_builds failed")
            return ToolResult(content=f"Error finding your builds: {e}", is_error=True)

    # ------------------------------------------------------------------
    # jenkins_search — find jobs by name across all folders
    # ------------------------------------------------------------------
    async def search_handler(args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "")
        if not query:
            return ToolResult(content="Error: query is required.", is_error=True)
        folder = args.get("folder", "")
        server = args.get("server")
        try:
            client = _get_client(server)
            all_jobs = await client.walk_jobs(folder, max_depth=5)
            # Case-insensitive substring match on name or fullPath
            q_lower = query.lower()
            matches = [j for j in all_jobs if q_lower in j.get("fullPath", "").lower()]
            if not matches:
                return ToolResult(content=f"No jobs matching \"{query}\" found.")
            lines = [f"**Search: \"{query}\"** ({len(matches)} matches):\n"]
            for job in matches[:20]:
                status = _color_to_status(job.get("color", ""))
                lines.append(f"- **{job['fullPath']}** — {status}")
            if len(matches) > 20:
                lines.append(f"\n_({len(matches) - 20} more results omitted)_")
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("jenkins_search failed")
            return ToolResult(content=f"Error searching jobs: {e}", is_error=True)

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
    # jenkins_params — get job parameter definitions
    # ------------------------------------------------------------------
    async def params_handler(args: dict[str, Any]) -> ToolResult:
        job_name = args.get("job_name", "")
        if not job_name:
            return ToolResult(content="Error: job_name is required.", is_error=True)
        server = args.get("server")
        try:
            client = _get_client(server)
            params = await client.get_job_parameters(job_name)
            if not params:
                return ToolResult(content=f"**{job_name}** has no parameters (can be triggered directly).")
            lines = [f"**Parameters for {job_name}:**\n"]
            for p in params:
                required = "Required" if "required" in p.get("description", "").lower() else "Optional"
                default = p.get("default", "")
                default_str = f" (default: `{default}`)" if default else ""
                choices = p.get("choices")
                choices_str = f" — choices: {choices}" if choices else ""
                lines.append(f"- **{p['name']}** [{required}]{default_str}{choices_str}")
                if p.get("description"):
                    lines.append(f"  {p['description']}")
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("jenkins_params failed")
            return ToolResult(content=f"Error getting parameters: {e}", is_error=True)

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

    # ------------------------------------------------------------------
    # jenkins_history — build history
    # ------------------------------------------------------------------
    async def history_handler(args: dict[str, Any]) -> ToolResult:
        job_name = args.get("job_name", "")
        if not job_name:
            return ToolResult(content="Error: job_name is required.", is_error=True)
        limit = int(args.get("limit") or 10)
        server = args.get("server")
        try:
            builds = await _get_client(server).get_build_history(job_name, limit)
            if not builds:
                return ToolResult(content=f"No build history for {job_name}.")
            lines = [f"**Build History — {job_name}** (last {len(builds)}):\n"]
            for b in builds:
                num = b.get("number", "?")
                result = b.get("result") or ("Building..." if b.get("building") else "Pending")
                duration = _duration_str(b.get("duration"))
                started = _ts_to_str(b.get("timestamp"))
                lines.append(f"- #{num} — **{result}** ({duration}) — {started}")
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("jenkins_history failed")
            return ToolResult(content=f"Error getting build history: {e}", is_error=True)

    # ------------------------------------------------------------------
    # jenkins_test_results — test report from a build
    # ------------------------------------------------------------------
    async def test_results_handler(args: dict[str, Any]) -> ToolResult:
        job_name = args.get("job_name", "")
        if not job_name:
            return ToolResult(content="Error: job_name is required.", is_error=True)
        build_number = args.get("build_number", "lastBuild")
        server = args.get("server")
        try:
            report = await _get_client(server).get_test_results(job_name, build_number)
            if not report:
                return ToolResult(content=f"No test results for {job_name} #{build_number}. The job may not produce a test report.")
            passed = report.get("passCount", 0)
            failed = report.get("failCount", 0)
            skipped = report.get("skipCount", 0)
            duration = report.get("duration", 0)
            total = passed + failed + skipped
            lines = [
                f"**Test Results — {job_name} #{build_number}**\n",
                f"**Total:** {total} | **Passed:** {passed} | **Failed:** {failed} | **Skipped:** {skipped}",
                f"**Duration:** {duration:.1f}s",
            ]
            # Show failed tests
            if failed > 0:
                lines.append("\n**Failed Tests:**")
                for suite in report.get("suites", []):
                    for case in suite.get("cases", []):
                        if case.get("status") in ("FAILED", "REGRESSION"):
                            name = case.get("name", "?")
                            error = case.get("errorDetails", "")
                            lines.append(f"- **{suite.get('name', '')}/{name}**")
                            if error:
                                lines.append(f"  ```\n  {error[:300]}\n  ```")
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("jenkins_test_results failed")
            return ToolResult(content=f"Error getting test results: {e}", is_error=True)

    # ------------------------------------------------------------------
    # jenkins_cancel_queue — cancel a queued item
    # ------------------------------------------------------------------
    async def cancel_queue_handler(args: dict[str, Any]) -> ToolResult:
        queue_id = args.get("queue_id")
        if queue_id is None:
            return ToolResult(content="Error: queue_id is required.", is_error=True)
        server = args.get("server")
        try:
            await _get_client(server).cancel_queue_item(int(queue_id))
            return ToolResult(content=f"Queue item {queue_id} cancelled.")
        except Exception as e:
            log.exception("jenkins_cancel_queue failed")
            return ToolResult(content=f"Error cancelling queue item: {e}", is_error=True)

    # ------------------------------------------------------------------
    # jenkins_enable / jenkins_disable — toggle job state
    # ------------------------------------------------------------------
    async def enable_handler(args: dict[str, Any]) -> ToolResult:
        job_name = args.get("job_name", "")
        if not job_name:
            return ToolResult(content="Error: job_name is required.", is_error=True)
        server = args.get("server")
        try:
            await _get_client(server).enable_job(job_name)
            return ToolResult(content=f"Job **{job_name}** enabled.")
        except Exception as e:
            log.exception("jenkins_enable failed")
            return ToolResult(content=f"Error enabling job: {e}", is_error=True)

    async def disable_handler(args: dict[str, Any]) -> ToolResult:
        job_name = args.get("job_name", "")
        if not job_name:
            return ToolResult(content="Error: job_name is required.", is_error=True)
        server = args.get("server")
        try:
            await _get_client(server).disable_job(job_name)
            return ToolResult(content=f"Job **{job_name}** disabled.")
        except Exception as e:
            log.exception("jenkins_disable failed")
            return ToolResult(content=f"Error disabling job: {e}", is_error=True)

    # ------------------------------------------------------------------
    # jenkins_system — system information
    # ------------------------------------------------------------------
    async def system_handler(args: dict[str, Any]) -> ToolResult:
        server = args.get("server")
        try:
            info = await _get_client(server).get_system_info()
            lines = [
                "**Jenkins System Info**\n",
                f"**Mode:** {info.get('mode', '?')}",
                f"**Executors:** {info.get('numExecutors', '?')}",
                f"**Description:** {info.get('nodeDescription', '')}",
                f"**Quieting Down:** {info.get('quietingDown', False)}",
            ]
            pv = info.get("primaryView", {})
            if pv:
                lines.append(f"**Primary View:** {pv.get('name', '?')}")
            return ToolResult(content="\n".join(lines))
        except Exception as e:
            log.exception("jenkins_system failed")
            return ToolResult(content=f"Error getting system info: {e}", is_error=True)

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
            name="jenkins_search",
            description="Search for Jenkins jobs by name across all folders. Finds jobs matching a keyword anywhere in the folder hierarchy.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term (matches job name or full path, case-insensitive).",
                    },
                    "folder": {
                        "type": "string",
                        "description": "Starting folder to search from (empty for root).",
                    },
                    "server": server_prop,
                },
                "required": ["query"],
            },
            handler=search_handler,
        ),
        Tool(
            name="jenkins_my_builds",
            description="Find recent builds triggered by the current user. Scans jobs in a folder for builds you started.",
            parameters={
                "type": "object",
                "properties": {
                    "folder": {
                        "type": "string",
                        "description": "Folder to search in (empty for root — can be slow on large instances).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max builds to return (default 20).",
                    },
                    "server": server_prop,
                },
            },
            handler=my_builds_handler,
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
            name="jenkins_params",
            description="Get parameter definitions for a Jenkins job. Shows what inputs are needed before triggering a build.",
            parameters={
                "type": "object",
                "properties": {
                    "job_name": {
                        "type": "string",
                        "description": "Name of the Jenkins job.",
                    },
                    "server": server_prop,
                },
                "required": ["job_name"],
            },
            handler=params_handler,
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
        Tool(
            name="jenkins_history",
            description="Get build history for a Jenkins job — shows recent builds with results and duration.",
            parameters={
                "type": "object",
                "properties": {
                    "job_name": {
                        "type": "string",
                        "description": "Name of the Jenkins job.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of recent builds to return. Default: 10.",
                    },
                    "server": server_prop,
                },
                "required": ["job_name"],
            },
            handler=history_handler,
        ),
        Tool(
            name="jenkins_test_results",
            description="Get test results (JUnit/xUnit) from a Jenkins build. Shows pass/fail counts and failed test details.",
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
                    "server": server_prop,
                },
                "required": ["job_name"],
            },
            handler=test_results_handler,
        ),
        Tool(
            name="jenkins_cancel_queue",
            description="Cancel an item waiting in the Jenkins build queue.",
            parameters={
                "type": "object",
                "properties": {
                    "queue_id": {
                        "type": "integer",
                        "description": "Queue item ID (from jenkins_queue output).",
                    },
                    "server": server_prop,
                },
                "required": ["queue_id"],
            },
            handler=cancel_queue_handler,
        ),
        Tool(
            name="jenkins_enable",
            description="Enable a disabled Jenkins job.",
            parameters={
                "type": "object",
                "properties": {
                    "job_name": {
                        "type": "string",
                        "description": "Name of the Jenkins job to enable.",
                    },
                    "server": server_prop,
                },
                "required": ["job_name"],
            },
            handler=enable_handler,
        ),
        Tool(
            name="jenkins_disable",
            description="Disable a Jenkins job (prevents new builds).",
            parameters={
                "type": "object",
                "properties": {
                    "job_name": {
                        "type": "string",
                        "description": "Name of the Jenkins job to disable.",
                    },
                    "server": server_prop,
                },
                "required": ["job_name"],
            },
            handler=disable_handler,
        ),
        Tool(
            name="jenkins_system",
            description="Get Jenkins system information — mode, executor count, status.",
            parameters={
                "type": "object",
                "properties": {
                    "server": server_prop,
                },
            },
            handler=system_handler,
        ),
    ]
