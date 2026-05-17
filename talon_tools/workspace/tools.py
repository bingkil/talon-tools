"""Sandboxed file system tool definitions for LLM agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from talon_tools import Tool, ToolResult
from .fs import ws_read, ws_write, ws_list, ws_delete, ws_append, ws_update, ws_grep


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

    async def append_handler(args: dict[str, Any]) -> ToolResult:
        return ToolResult(content=ws_append(
            root_dir,
            args.get("path", ""),
            args.get("content", ""),
            args.get("separator", "\n\n"),
        ))

    async def update_handler(args: dict[str, Any]) -> ToolResult:
        return ToolResult(content=ws_update(
            root_dir,
            args.get("path", ""),
            args.get("section", ""),
            args.get("content", ""),
            args.get("level", 2),
            args.get("create_if_missing", True),
        ))

    async def grep_handler(args: dict[str, Any]) -> ToolResult:
        return ToolResult(content=ws_grep(
            root_dir,
            args.get("pattern", ""),
            args.get("glob", "**/*"),
            args.get("case_insensitive", True),
            args.get("context_lines", 1),
            args.get("max_results", 20),
            args.get("regex", False),
        ))

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
        Tool(
            name="ws_append",
            description=(
                "Append content to a workspace file without overwriting it. "
                "Creates the file if it doesn't exist. "
                "Use instead of ws_write when you want to add to existing content."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Workspace-relative file path"},
                    "content": {"type": "string", "description": "Content to append"},
                    "separator": {
                        "type": "string",
                        "description": "Separator inserted before new content (default: two newlines)",
                    },
                },
                "required": ["path", "content"],
            },
            handler=append_handler,
        ),
        Tool(
            name="ws_update",
            description=(
                "Upsert a named Markdown section in a workspace file. "
                "If the section heading exists, its content is replaced. "
                "If not, the section is appended. "
                "Use this to update one section of a note without touching the rest."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Workspace-relative file path"},
                    "section": {
                        "type": "string",
                        "description": "Section heading text (without the # symbols), e.g. 'Talon relevance'",
                    },
                    "content": {
                        "type": "string",
                        "description": "New content for the section (do not include the heading line)",
                    },
                    "level": {
                        "type": "integer",
                        "description": "Heading level: 2 for ##, 3 for ###, etc. Default: 2",
                    },
                    "create_if_missing": {
                        "type": "boolean",
                        "description": "Create the file if it doesn't exist. Default: true",
                    },
                },
                "required": ["path", "section", "content"],
            },
            handler=update_handler,
        ),
        Tool(
            name="ws_grep",
            description=(
                "Search for text across all files in the workspace. "
                "Use this to find notes, facts, or references without knowing the exact filename. "
                "Returns matching lines with file paths and line numbers."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Text to search for (plain string by default, or regex if regex=true)",
                    },
                    "glob": {
                        "type": "string",
                        "description": "File glob to limit search scope, e.g. 'notes/*.md' or '**/*.py'. Default: all text files.",
                    },
                    "case_insensitive": {
                        "type": "boolean",
                        "description": "Case-insensitive matching. Default: true.",
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "Lines of context to show around each match. Default: 1.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of matches to return. Default: 20.",
                    },
                    "regex": {
                        "type": "boolean",
                        "description": "Treat pattern as a regular expression. Default: false.",
                    },
                },
                "required": ["pattern"],
            },
            handler=grep_handler,
        ),
    ]
