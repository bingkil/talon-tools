"""MCP HTTP client — stateless JSON-RPC over HTTP.

Implements just enough of the MCP protocol to:
1. Initialize a session
2. List available tools
3. Call tools

Designed for servers using streamable HTTP transport (fastmcp style).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class MCPClientError(Exception):
    """Error communicating with an MCP server."""


class MCPClient:
    """Stateless MCP client that communicates over HTTP POST (JSON-RPC 2.0)."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 60.0,
    ):
        self.url = url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send a JSON-RPC 2.0 request and return the result."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params:
            payload["params"] = params

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self.url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    **self.headers,
                },
            )

        if resp.status_code != 200:
            raise MCPClientError(
                f"MCP server returned {resp.status_code}: {resp.text[:500]}"
            )

        body = resp.json()

        if "error" in body:
            err = body["error"]
            raise MCPClientError(
                f"MCP error {err.get('code')}: {err.get('message', 'unknown')}"
            )

        return body.get("result")

    async def initialize(self) -> dict[str, Any]:
        """Send initialize request. Returns server capabilities."""
        result = await self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "talon-mcp", "version": "0.1.0"},
        })
        return result or {}

    async def list_tools(self) -> list[dict[str, Any]]:
        """List tools available on the server."""
        result = await self._rpc("tools/list")
        if result is None:
            return []
        return result.get("tools", [])

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool and return its text content."""
        result = await self._rpc("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        if result is None:
            return ""

        # MCP tools return content as a list of content blocks
        content_blocks = result.get("content", [])
        texts = []
        for block in content_blocks:
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
        return "\n".join(texts) if texts else str(result)
