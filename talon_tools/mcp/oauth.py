"""Runtime OAuth token provider for remote MCP servers (e.g. Atlassian Rovo).

Agents never perform the OAuth dance themselves. Instead the always-running Nest
daemon owns the encrypted refresh token and acts as a token broker: it refreshes
(and persists the rotating refresh token) on demand and hands back a short-lived
access token. This keeps refresh-token rotation race-free across many agent
processes.

`NestTokenProvider` is a callable suitable for `MCPClient(token_provider=...)`:
it caches the access token locally and only calls the broker when the token is
missing, near expiry, or a forced refresh is requested (after a 401).
"""

from __future__ import annotations

import logging
import os
import time

import httpx

log = logging.getLogger(__name__)


def nest_base_url() -> str:
    """Resolve the local Nest base URL (token broker host)."""
    url = os.environ.get("TALON_NEST_URL")
    if url:
        return url.rstrip("/")
    port = os.environ.get("TALON_NEST_PORT", "3100")
    return f"http://127.0.0.1:{port}"


class NestTokenProvider:
    """Fetch OAuth access tokens for one MCP server from the Nest broker."""

    def __init__(self, agent: str, server: str, base_url: str | None = None):
        self.agent = agent
        self.server = server
        self.base_url = (base_url or nest_base_url()).rstrip("/")
        self._token: str | None = None
        self._expires_at: float = 0.0  # epoch seconds

    def __call__(self, force: bool = False) -> str:
        now = time.time()
        if not force and self._token and self._expires_at - now > 60:
            return self._token

        endpoint = f"{self.base_url}/api/mcp/oauth/token"
        try:
            resp = httpx.get(
                endpoint,
                params={"agent": self.agent, "server": self.server},
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise RuntimeError(f"token broker unreachable at {endpoint}: {e}") from e

        if resp.status_code != 200:
            raise RuntimeError(
                f"token broker returned {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError("token broker returned no access_token")
        self._token = token
        exp_ms = data.get("expires_at")
        self._expires_at = (exp_ms / 1000.0) if exp_ms else (now + 300)
        return token
