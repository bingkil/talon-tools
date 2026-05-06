"""Sandboxed file system tool definitions for LLM agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from talon_tools import Tool, ToolResult
from .fs import ws_read, ws_write, ws_list, ws_delete


def build_tools(root_dir: Path) -> list[Tool]:
    """Return workspace file tools bound to the given root directory."""

    async def read_handler(args: dict[str, Any]) -> ToolResult:
        return ToolResult(content=ws_read(root_dir, args.get("path", "")))

    async def write_handler(args: dict[str, Any]) -> ToolResult:
        return ToolResult(content=ws_write(root_dir, args.get("path", ""), args.get("content", "")))

    async def list_handler(args: dict[str, Any]) -> ToolResult:
        return ToolResult(content=ws_list(root_dir, args.get("path", "")))

    async def delete_handler(args: dict[str, Any]) -> ToolResult:
        return ToolResult(content=ws_delete(root_dir, args.get("path", "")))

    return [
        Tool(
            name="ws_read",
            description="Read a file from the workspace. Use relative paths.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path within workspace"},
                },
                "required": ["path"],
            },
            handler=read_handler,
        ),
        Tool(
            name="ws_write",
            description=(
                "Create or overwrite a file in the workspace. "
                "Directories are created automatically. Use relative paths."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path within workspace"},
                    "content": {"type": "string", "description": "File content to write"},
                },
                "required": ["path", "content"],
            },
            handler=write_handler,
        ),
        Tool(
            name="ws_list",
            description="List files and directories in the workspace. Omit path or use '' for root.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path (empty for root)"},
                },
            },
            handler=list_handler,
        ),
        Tool(
            name="ws_delete",
            description="Delete a file or directory from the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file or directory path to delete"},
                },
                "required": ["path"],
            },
            handler=delete_handler,
        ),
    ]
