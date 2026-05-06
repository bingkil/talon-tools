"""Tool definitions for document reader skill."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from talon_tools import Tool, ToolResult
from .reader import read_document, SUPPORTED_EXTENSIONS

log = logging.getLogger(__name__)


def build_tools(root_dir: Path | None = None) -> list[Tool]:
    """Return document reader tools, optionally sandboxed to root_dir."""

    async def read_handler(args: dict[str, Any]) -> ToolResult:
        file_path = args.get("path", "")
        if not file_path:
            return ToolResult(content="Error: path is required", is_error=True)

        p = Path(file_path)

        # If sandboxed, resolve relative to root
        if root_dir and not p.is_absolute():
            p = root_dir / p

        try:
            text = read_document(p)
            # Truncate very large documents
            if len(text) > 50_000:
                text = text[:50_000] + "\n\n---\n⚠️ Document truncated (>50k chars). Showing first portion."
            return ToolResult(content=text)
        except FileNotFoundError as e:
            return ToolResult(content=f"Error: {e}", is_error=True)
        except ValueError as e:
            return ToolResult(content=f"Error: {e}", is_error=True)
        except Exception as e:
            log.exception("doc_read failed")
            return ToolResult(content=f"Error reading document: {e}", is_error=True)

    exts = ", ".join(sorted(SUPPORTED_EXTENSIONS))

    return [
        Tool(
            name="doc_read",
            description=(
                f"Read and extract text from a document file. "
                f"Supported formats: {exts}. "
                f"Returns the document content as markdown-formatted text. "
                f"For Excel files, each sheet is rendered as a table. "
                f"For PowerPoint, each slide's text is extracted."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the document file (absolute or relative to workspace).",
                    },
                },
                "required": ["path"],
            },
            handler=read_handler,
        ),
    ]
