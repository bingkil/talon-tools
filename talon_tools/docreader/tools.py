"""Tool definitions for document reader skill."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from talon_tools import Tool, ToolResult
from .reader import read_document, SUPPORTED_EXTENSIONS

log = logging.getLogger(__name__)


def build_tools(root_dir: Path | None = None, agent_dir: Path | None = None, **_kwargs) -> list[Tool]:
    if root_dir is None:
        root_dir = agent_dir
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

    async def screenshot_handler(args: dict[str, Any]) -> ToolResult:
        file_path = args.get("path", "")
        page_num = args.get("page", 1)
        if not file_path:
            return ToolResult(content="Error: path is required", is_error=True)

        try:
            from liteparse import LiteParse
        except ImportError:
            return ToolResult(content="Error: doc_screenshot requires liteparse (pip install liteparse)", is_error=True)

        p = Path(file_path)
        if root_dir and not p.is_absolute():
            p = root_dir / p

        if not p.exists():
            return ToolResult(content=f"Error: File not found: {p}", is_error=True)

        try:
            parser = LiteParse(quiet=True)
            results = parser.screenshot(p, page_numbers=[page_num])
            if not results:
                return ToolResult(content=f"Error: No screenshot generated for page {page_num}", is_error=True)
            png_bytes = results[0].data
            b64 = base64.b64encode(png_bytes).decode()
            return ToolResult(content=f"[Page {page_num} screenshot: {len(png_bytes)} bytes PNG]\ndata:image/png;base64,{b64}")
        except Exception as e:
            log.exception("doc_screenshot failed")
            return ToolResult(content=f"Error: {e}", is_error=True)

    return [
        Tool(
            name="doc_read",
            description=(
                f"Read and extract text from a document file. "
                f"Supported formats: {exts}. "
                f"Returns the document content as markdown-formatted text. "
                f"Uses LiteParse v2 (Rust-based, with OCR) for PDF/DOCX when available. "
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
        Tool(
            name="doc_screenshot",
            description=(
                "Render a specific page of a PDF or DOCX as a PNG image. "
                "Returns base64-encoded PNG data. Useful for visual analysis "
                "of charts, diagrams, layouts, or scanned content that text "
                "extraction cannot capture."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the document file.",
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number to screenshot (1-indexed, default 1).",
                    },
                },
                "required": ["path"],
            },
            handler=screenshot_handler,
        ),
    ]
