"""MCP stdio server exposing talon-tools to IDEs."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import sys
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool as MCPTool

from talon_tools import Tool
from talon_tools import credentials
from talon_tools.cli import _CredStoreProvider

log = logging.getLogger(__name__)

_SKIP_MODULES = {"onboarding", "providers", "__pycache__", "channels"}


def _discover_and_build(only: set[str] | None = None) -> tuple[list[Tool], dict[str, list[str]]]:
    """Import tool modules and call build_tools(). Skip failures silently.

    Returns (tools, module_tools) where module_tools maps module name to tool names.
    """
    import importlib

    pkg_dir = Path(__file__).parent
    tools: list[Tool] = []
    module_tools: dict[str, list[str]] = {}

    for child in sorted(pkg_dir.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        if child.name in _SKIP_MODULES:
            continue
        if not (child / "tools.py").exists():
            continue
        if only and child.name not in only:
            continue

        try:
            mod = importlib.import_module(f"talon_tools.{child.name}.tools")
            fn = mod.build_tools
            sig = inspect.signature(fn)

            # Build dummy args for required params (e.g. root_dir for workspace)
            kwargs = {}
            for name, param in sig.parameters.items():
                if param.default is inspect.Parameter.empty and param.kind in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                ):
                    ann = param.annotation
                    if ann is Path or (isinstance(ann, str) and "Path" in ann):
                        kwargs[name] = Path.cwd()
                    elif ann is str or (isinstance(ann, str) and "str" in ann):
                        kwargs[name] = ""
                    else:
                        kwargs[name] = None

            built = fn(**kwargs)
            tools.extend(built)
            module_tools[child.name] = [t.name for t in built]
        except Exception as e:
            log.debug(f"Skipping {child.name}: {e}")
            continue

    return tools, module_tools


def _credential_status() -> dict:
    """Return configured/missing credential status."""
    from talon_tools.credentials import list_credentials, get

    configured = []
    missing: dict[str, list[str]] = {}

    all_reqs = list_credentials()
    for tool_name, reqs in all_reqs.items():
        missing_keys = []
        for req in reqs:
            try:
                get(req.key)
            except (KeyError, Exception):
                if req.required:
                    missing_keys.append(req.key)
        if missing_keys:
            missing[tool_name] = missing_keys
        else:
            configured.append(tool_name)

    return {"configured": configured, "missing": missing}


def create_server(tools: list[Tool]) -> Server:
    """Create and configure the MCP server with pre-loaded tools."""
    server = Server("talon-tools")

    # Build lookup for dispatch
    tool_map: dict[str, Tool] = {t.name: t for t in tools}

    @server.list_tools()
    async def list_tools():
        return [
            MCPTool(
                name=t.name,
                description=t.description,
                inputSchema=t.parameters,
            )
            for t in tools
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        tool = tool_map.get(name)
        if not tool:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        try:
            result = await tool.handler(arguments)
            return [TextContent(type="text", text=result.content)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {e}")]

    @server.list_resources()
    async def list_resources():
        from mcp.types import Resource
        return [
            Resource(
                uri="talon-tools://credentials/status",
                name="Credential Status",
                description="Shows which tools are configured and which are missing credentials",
                mimeType="application/json",
            )
        ]

    @server.read_resource()
    async def read_resource(uri):
        if str(uri) == "talon-tools://credentials/status":
            import json
            status = _credential_status()
            return json.dumps(status, indent=2)
        raise ValueError(f"Unknown resource: {uri}")

    return server


async def run(tools_filter: set[str] | None = None, creds_path: str | None = None):
    """Initialize credentials and run the MCP server over stdio."""
    from talon_tools.cli import _resolve_creds_path

    resolved = _resolve_creds_path(creds_path)
    credentials.init(_CredStoreProvider(resolved))

    # Startup banner (stderr — stdout is the MCP transport)
    print("Talon Tools MCP Server starting...", file=sys.stderr)
    print(f"  Credentials: {resolved}", file=sys.stderr)

    tools, module_tools = _discover_and_build(only=tools_filter)

    # Use the onboarding registry (same as `setup --status`) for readiness
    from talon_tools.onboarding.registry import get_all_onboardings

    registry = get_all_onboardings()
    ready = []
    unavailable = []
    for name, ob in registry.items():
        if ob.setup_type == "zero" or ob.is_configured():
            ready.append(name)
        else:
            unavailable.append(name)

    print(f"  Modules: {len(module_tools)} loaded", file=sys.stderr)
    if ready:
        print(f"  Ready: {', '.join(sorted(ready))}", file=sys.stderr)
    if unavailable:
        print(f"  Unavailable (missing creds): {', '.join(sorted(unavailable))}", file=sys.stderr)
    print(f"  Tools: {len(tools)} total", file=sys.stderr)
    print("  Transport: stdio", file=sys.stderr)
    print("  Ready.", file=sys.stderr)

    server = create_server(tools)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


def main():
    """Entry point for `talon-tools mcp`."""
    import argparse

    parser = argparse.ArgumentParser(description="talon-tools MCP server (stdio)")
    parser.add_argument(
        "--tools",
        help="Comma-separated list of modules to load (e.g. atlassian,google,jenkins)",
    )
    parser.add_argument(
        "--creds", metavar="PATH",
        help="Path to credentials file (.env or .yaml)",
    )
    args = parser.parse_args()

    tools_filter = set(args.tools.split(",")) if args.tools else None
    asyncio.run(run(tools_filter, creds_path=args.creds))


if __name__ == "__main__":
    main()
