"""MCP HTTP client — stateless JSON-RPC over HTTP.

Implements just enough of the MCP protocol to:
1. Initialize a session
2. List available tools
3. Call tools

Designed for servers using streamable HTTP transport (fastmcp style).
"""

from __future__ import annotations

import json
import logging
import ssl
from typing import Any, Callable

import httpx

log = logging.getLogger(__name__)


def _build_ssl_context() -> ssl.SSLContext | bool:
    """Return an SSL context that trusts the OS certificate store.

    In corporate environments an inspecting proxy presents certificates signed
    by a private root CA that is installed in the OS trust store (e.g. the
    Windows cert store) but is absent from certifi's bundle, which is what httpx
    verifies against by default. ``truststore`` bridges that gap by delegating
    verification to the platform store. Falls back to httpx's default
    verification if ``truststore`` is unavailable.
    """
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # noqa: BLE001 — any failure ⇒ keep default verification
        return True


# Built once per process; honours the platform trust store when available.
_SSL_CONTEXT: ssl.SSLContext | bool = _build_ssl_context()


class MCPClientError(Exception):
    """Error communicating with an MCP server.

    Carries the HTTP status and any ``WWW-Authenticate`` challenge header so
    callers (e.g. the probe) can distinguish an auth requirement (401 advertising
    OAuth) from other failures and pick the right authentication flow.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        www_authenticate: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.www_authenticate = www_authenticate


class MCPClient:
    """Stateless MCP client that communicates over HTTP POST (JSON-RPC 2.0)."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 60.0,
        token_provider: Callable[[bool], str] | None = None,
    ):
        self.url = url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout
        # Optional OAuth bearer-token provider. Called as provider(force) -> token;
        # `force=True` requests a fresh token (used to recover from a 401).
        self.token_provider = token_provider
        self._request_id = 0
        self._session_id: str | None = None
        self._initialized = False

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    @staticmethod
    def _parse_sse(text: str) -> dict[str, Any]:
        """Extract the last JSON-RPC message from an SSE stream."""
        result: dict[str, Any] = {}
        for line in text.splitlines():
            if line.startswith("data: "):
                try:
                    result = json.loads(line[6:])
                except json.JSONDecodeError:
                    pass
        return result

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send a JSON-RPC 2.0 request and return the result."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params:
            payload["params"] = params

        async def _send(force_token: bool) -> httpx.Response:
            req_headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                **self.headers,
            }
            if self.token_provider is not None:
                import asyncio

                token = await asyncio.to_thread(self.token_provider, force_token)
                if token:
                    req_headers["Authorization"] = f"Bearer {token}"
            if self._session_id:
                req_headers["Mcp-Session-Id"] = self._session_id
            async with httpx.AsyncClient(timeout=self.timeout, verify=_SSL_CONTEXT) as client:
                return await client.post(self.url, json=payload, headers=req_headers)

        resp = await _send(False)
        # OAuth access tokens expire — on 401, force a refresh and retry once.
        if resp.status_code == 401 and self.token_provider is not None:
            resp = await _send(True)

        if resp.status_code != 200:
            raise MCPClientError(
                f"MCP server returned {resp.status_code}: {resp.text[:500]}",
                status_code=resp.status_code,
                www_authenticate=resp.headers.get("www-authenticate"),
            )

        # Capture session ID from response
        session_id = resp.headers.get("mcp-session-id")
        if session_id:
            self._session_id = session_id

        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            body = self._parse_sse(resp.text)
        else:
            body = resp.json()

        if "error" in body:
            err = body["error"]
            raise MCPClientError(
                f"MCP error {err.get('code')}: {err.get('message', 'unknown')}"
            )

        return body.get("result")

    async def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send a JSON-RPC 2.0 notification (no id, no response expected)."""
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params

        req_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self.headers,
        }
        if self.token_provider is not None:
            import asyncio

            token = await asyncio.to_thread(self.token_provider, False)
            if token:
                req_headers["Authorization"] = f"Bearer {token}"
        if self._session_id:
            req_headers["Mcp-Session-Id"] = self._session_id
        async with httpx.AsyncClient(timeout=self.timeout, verify=_SSL_CONTEXT) as client:
            resp = await client.post(self.url, json=payload, headers=req_headers)
        # Notifications return 202 Accepted (or 200); anything else is fatal.
        if resp.status_code not in (200, 202, 204):
            raise MCPClientError(
                f"MCP server rejected {method}: {resp.status_code} {resp.text[:200]}"
            )

    async def initialize(self) -> dict[str, Any]:
        """Run the MCP handshake: initialize, then notifications/initialized.

        Per the MCP spec a client MUST send the `notifications/initialized`
        notification after a successful `initialize` before issuing any other
        request. Spec-compliant streamable-HTTP servers (e.g. Atlassian Rovo)
        refuse `tools/call` until this completes; lenient servers tolerate its
        absence, which is why the gap went unnoticed against fastmcp servers.
        """
        result = await self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "talon-mcp", "version": "0.1.0"},
        })
        await self._notify("notifications/initialized")
        self._initialized = True
        return result or {}

    async def _ensure_session(self) -> None:
        """Lazily establish the MCP session before list/call operations."""
        if not self._initialized:
            await self.initialize()

    async def list_tools(self) -> list[dict[str, Any]]:
        """List tools available on the server."""
        await self._ensure_session()
        result = await self._rpc("tools/list")
        if result is None:
            return []
        return result.get("tools", [])

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool and return its text content."""
        await self._ensure_session()
        try:
            result = await self._rpc("tools/call", {
                "name": name,
                "arguments": arguments,
            })
        except MCPClientError as e:
            # A 404 means the server dropped our session — re-handshake once.
            if "404" in str(e):
                self._initialized = False
                self._session_id = None
                await self._ensure_session()
                result = await self._rpc("tools/call", {
                    "name": name,
                    "arguments": arguments,
                })
            else:
                raise
        if result is None:
            return ""

        # MCP tools return content as a list of content blocks
        content_blocks = result.get("content", [])
        texts = []
        for block in content_blocks:
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
        return "\n".join(texts) if texts else str(result)
