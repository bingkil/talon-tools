"""HTTP request tool — make arbitrary HTTP calls from an LLM agent."""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx

from talon_tools import Tool, ToolResult


async def http_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    form_data: dict[str, str] | None = None,
    auth_bearer: str | None = None,
    auth_basic: str | None = None,
    timeout: float = 30.0,
    max_response_bytes: int = 4000,
    follow_redirects: bool = True,
) -> str:
    """Execute an HTTP request and return a structured summary."""
    request_headers = headers.copy() if headers else {}

    if auth_bearer:
        request_headers["Authorization"] = f"Bearer {auth_bearer}"
    elif auth_basic:
        encoded = base64.b64encode(auth_basic.encode()).decode()
        request_headers["Authorization"] = f"Basic {encoded}"

    if body and "Content-Type" not in request_headers:
        request_headers["Content-Type"] = "application/json"

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=follow_redirects
        ) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=request_headers,
                params=params,
                json=body if body else None,
                data=form_data if form_data else None,
            )
        elapsed_ms = int((time.monotonic() - start) * 1000)

        raw = response.content
        truncated = len(raw) > max_response_bytes
        body_sample = raw[:max_response_bytes]

        # Try to parse as JSON for pretty-printing
        try:
            parsed = response.json()
            body_text = json.dumps(parsed, indent=2)
            if len(body_text) > max_response_bytes:
                body_text = body_text[:max_response_bytes] + "\n... (truncated)"
        except Exception:
            try:
                body_text = body_sample.decode("utf-8", errors="replace")
            except Exception:
                body_text = f"<binary {len(raw)} bytes>"
            if truncated:
                body_text += "\n... (truncated)"

        lines = [
            f"Status: {response.status_code} {response.reason_phrase}",
            f"Time: {elapsed_ms}ms",
            f"Size: {len(raw)} bytes",
        ]

        useful_headers = [
            "content-type", "x-request-id", "retry-after",
            "location", "x-ratelimit-remaining",
        ]
        for h in useful_headers:
            if h in response.headers:
                lines.append(f"{h}: {response.headers[h]}")

        lines.append("")
        lines.append(body_text)
        return "\n".join(lines)

    except httpx.TimeoutException:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return f"TIMEOUT after {elapsed_ms}ms ({timeout}s limit)\nURL: {url}"
    except httpx.ConnectError as e:
        return f"CONNECTION ERROR: {e}\nURL: {url}"
    except Exception as e:
        return f"REQUEST ERROR: {type(e).__name__}: {e}\nURL: {url}"


def build_tools() -> list[Tool]:
    """Return the http_request tool."""

    async def handler(args: dict[str, Any]) -> ToolResult:
        result = await http_request(
            url=args.get("url", ""),
            method=args.get("method", "GET"),
            headers=args.get("headers"),
            params=args.get("params"),
            body=args.get("body"),
            form_data=args.get("form_data"),
            auth_bearer=args.get("auth_bearer"),
            auth_basic=args.get("auth_basic"),
            timeout=args.get("timeout", 30.0),
            max_response_bytes=args.get("max_response_bytes", 4000),
            follow_redirects=args.get("follow_redirects", True),
        )
        return ToolResult(content=result)

    return [
        Tool(
            name="http_request",
            description=(
                "Make an HTTP request to any URL. Returns status code, response time, "
                "and response body (truncated to keep token cost low). "
                "Use for REST APIs, webhooks, health checks, and any HTTP endpoint "
                "not covered by a dedicated tool."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
                        "description": "HTTP method. Default: GET",
                    },
                    "url": {
                        "type": "string",
                        "description": "Full URL including scheme (https://...)",
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional request headers as key-value pairs",
                        "additionalProperties": {"type": "string"},
                    },
                    "params": {
                        "type": "object",
                        "description": "Optional query string parameters as key-value pairs",
                        "additionalProperties": {"type": "string"},
                    },
                    "body": {
                        "type": "object",
                        "description": "Optional request body (sent as JSON). For form data use form_data instead.",
                    },
                    "form_data": {
                        "type": "object",
                        "description": "Optional form-encoded body (application/x-www-form-urlencoded)",
                        "additionalProperties": {"type": "string"},
                    },
                    "auth_bearer": {
                        "type": "string",
                        "description": "Bearer token added as Authorization: Bearer <token> header",
                    },
                    "auth_basic": {
                        "type": "string",
                        "description": "Basic auth credentials in username:password format",
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Request timeout in seconds. Default: 30",
                    },
                    "max_response_bytes": {
                        "type": "integer",
                        "description": "Truncate response body to this many bytes. Default: 4000",
                    },
                    "follow_redirects": {
                        "type": "boolean",
                        "description": "Follow HTTP redirects. Default: true",
                    },
                },
                "required": ["url"],
            },
            handler=handler,
        ),
    ]


def build_rendered_tools() -> list[Tool]:
    """Return the web_fetch_rendered tool (requires Playwright)."""
    from .rendered import web_fetch_rendered

    async def handler(args: dict[str, Any]) -> ToolResult:
        result = await web_fetch_rendered(
            url=args.get("url", ""),
            wait_for_selector=args.get("wait_for_selector"),
            timeout_ms=args.get("timeout_ms", 15000),
        )
        return ToolResult(content=result)

    return [
        Tool(
            name="web_fetch_rendered",
            description=(
                "Fetch a web page with full JavaScript rendering using a headless browser. "
                "Use this when http_request returns empty/minimal content from JS-heavy sites "
                "(SPAs, React/Vue/Angular apps). Returns cleaned text content (no HTML). "
                "Slower than http_request (~5-15s) — only use when needed."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL to fetch (https://...)",
                    },
                    "wait_for_selector": {
                        "type": "string",
                        "description": "Optional CSS selector to wait for before extracting content",
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "description": "Navigation timeout in milliseconds. Default: 15000",
                    },
                },
                "required": ["url"],
            },
            handler=handler,
        ),
    ]
