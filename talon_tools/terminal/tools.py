"""Shell command execution tool definitions for LLM agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from talon_tools import Tool, ToolResult
from .shell import run_command


def build_tools(*, cwd: Path | None = None) -> list[Tool]:
    """Return terminal/shell tools.

    Args:
        cwd: Working directory for all commands. If set, commands are
             locked to this directory and cannot cd elsewhere.
    """

    async def handler(args: dict[str, Any]) -> ToolResult:
        command = args.get("command", "")
        timeout = args.get("timeout", 60)
        if not command:
            return ToolResult(content="Error: command is required", is_error=True)
        output = await run_command(command, timeout=min(timeout, 120), cwd=cwd)
        return ToolResult(content=output)

    cwd_note = f" Working directory is locked to {cwd}." if cwd else ""
    return [
        Tool(
            name="terminal",
            description=(
                "Run a shell command on the host machine and return its output. "
                "Use for system checks, file operations, package management, git, etc. "
                "Commands run in PowerShell on Windows, sh on Unix. Max timeout 120s. "
                "Destructive commands (rm -rf, Stop-Process, registry edits, etc.) are blocked."
                + cwd_note
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute"},
                    "timeout": {"type": "integer", "description": "Max seconds to wait (default 60, max 120)"},
                },
                "required": ["command"],
            },
            handler=handler,
        ),
    ]
