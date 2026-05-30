"""Build Talon tools from remote MCP servers."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import re
from typing import Any

from talon_tools import Tool, ToolResult
from talon_tools.credentials import get as cred
from .client import MCPClient, MCPClientError

log = logging.getLogger(__name__)


def _run_sync(coro):
    """Run an async coroutine from sync code, even inside a running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — safe to use asyncio.run()
        return asyncio.run(coro)
    # Already inside a running loop — offload to a thread
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)")

# Cache: keyed by frozenset of (server_name, url) tuples
_tools_cache: dict[frozenset, list[Tool]] = {}


def _cache_key(servers: list[dict[str, Any]]) -> frozenset:
    return frozenset((s.get("name", "mcp"), s.get("url", "")) for s in servers)


def _resolve_env(value: str) -> str:
    """Resolve $VAR or ${VAR} references in a string to credential/env values."""
    def _replace(m: re.Match) -> str:
        var = m.group(1) or m.group(2)
        return cred(var, "")
    return _ENV_PATTERN.sub(_replace, value)


def _resolve_headers(headers: dict[str, str] | None) -> dict[str, str] | None:
    """Resolve env vars in all header values."""
    if not headers:
        return headers
    return {k: _resolve_env(v) for k, v in headers.items()}


def build_tools(servers: list[dict[str, Any]]) -> list[Tool]:
    """Build Talon tools by connecting to MCP servers and discovering their tools.

    Results are cached for the sentinel session — MCP discovery only runs once
    per unique server set.

    Args:
        servers: List of server configs, each with:
            - name: Server name (used as tool prefix)
            - url: MCP server HTTP endpoint
            - headers: Optional dict of HTTP headers (for auth)
            - timeout: Optional request timeout in seconds

    Returns:
        List of Talon Tool objects wrapping remote MCP tools.
    """
    key = _cache_key(servers)
    if key in _tools_cache:
        return _tools_cache[key]

    import asyncio

    tools: list[Tool] = []
    for server_cfg in servers:
        name = server_cfg.get("name", "mcp")
        url = _resolve_env(server_cfg.get("url", ""))
        if not url:
            log.warning(f"MCP server '{name}' has no url, skipping")
            continue

        client = MCPClient(
            url=url,
            headers=_resolve_headers(server_cfg.get("headers")),
            timeout=server_cfg.get("timeout", 60.0),
        )

        try:
            remote_tools = _run_sync(_discover_tools(client))
        except Exception as e:
            log.error(f"Failed to discover tools from MCP server '{name}' at {url}: {e}")
            print(f"[MCP] WARNING: {name} tools unavailable — {e}", flush=True)
            continue

        for rt in remote_tools:
            tool = _wrap_remote_tool(client, name, rt)
            tools.append(tool)

        log.info(f"MCP server '{name}': discovered {len(remote_tools)} tools")
        print(f"[MCP] {name}: {len(remote_tools)} tools loaded", flush=True)

    _tools_cache[key] = tools
    return tools


async def _discover_tools(client: MCPClient) -> list[dict[str, Any]]:
    """Initialize connection and list tools."""
    await client.initialize()
    return await client.list_tools()


def _wrap_remote_tool(
    client: MCPClient,
    server_name: str,
    tool_def: dict[str, Any],
) -> Tool:
    """Wrap a remote MCP tool definition as a Talon Tool."""
    remote_name = tool_def.get("name", "unknown")
    description = tool_def.get("description", "")
    input_schema = tool_def.get("inputSchema", {"type": "object", "properties": {}})

    # Prefix tool name with server name to avoid collisions
    local_name = f"{server_name}__{remote_name}"

    async def handler(args: dict[str, Any], _client=client, _remote=remote_name) -> ToolResult:
        try:
            result = await _client.call_tool(_remote, args)
            return ToolResult(content=result)
        except MCPClientError as e:
            return ToolResult(content=f"MCP error: {e}", is_error=True)

    return Tool(
        name=local_name,
        description=f"[{server_name}] {description}",
        parameters=input_schema,
        handler=handler,
    )
