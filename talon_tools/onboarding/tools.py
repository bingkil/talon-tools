"""Onboarding tool definitions for LLM agents."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from talon_tools import Tool, ToolResult

from .base import ToolOnboarding
from .spotify import spotify_onboarding, get_auth_url, run_auth_flow, complete_auth, verify_connection
from .youtube import youtube_onboarding, verify_connection as youtube_verify_connection


# Registry of all service onboarding definitions
_SERVICES: dict[str, ToolOnboarding] = {
    "spotify": spotify_onboarding(),
    "youtube": youtube_onboarding(),
}


def build_tools(agent_dir: Path | None = None) -> list[Tool]:
    """Return onboarding tools."""

    async def handle_status(args: dict[str, Any]) -> ToolResult:
        """Check onboarding status for a service or all services."""
        service = args.get("service", "").strip().lower()

        if service:
            ob = _SERVICES.get(service)
            if not ob:
                available = ", ".join(_SERVICES.keys())
                return ToolResult(content=f"Unknown service: {service}. Available: {available}")

            status = ob.status()
            configured = ob.is_configured()
            next_step = ob.next_step()

            lines = [f"## {ob.display_name} — {'✓ Configured' if configured else '✗ Not configured'}"]
            for key, ok in status.items():
                lines.append(f"  {'✓' if ok else '✗'} {key}")
            if next_step:
                lines.append(f"\nNext step: {next_step.title}")
                lines.append(next_step.instruction)
            return ToolResult(content="\n".join(lines))

        # All services
        lines = ["## Onboarding Status\n"]
        for name, ob in _SERVICES.items():
            icon = "✓" if ob.is_configured() else "✗"
            lines.append(f"  {icon} {ob.display_name}")
        return ToolResult(content="\n".join(lines))

    async def handle_auth_url(args: dict[str, Any]) -> ToolResult:
        """Run the full OAuth flow: open browser, capture callback, exchange token."""
        service = args.get("service", "").strip().lower()

        if service == "spotify":
            try:
                result = await asyncio.to_thread(run_auth_flow, agent_dir)
                return ToolResult(content=result, is_error=result.startswith("Error"))
            except RuntimeError as e:
                return ToolResult(content=str(e), is_error=True)

        return ToolResult(content=f"OAuth not supported for: {service}", is_error=True)

    async def handle_complete_auth(args: dict[str, Any]) -> ToolResult:
        """Complete an OAuth flow by providing the redirect URL."""
        service = args.get("service", "").strip().lower()
        redirect_url = args.get("redirect_url", "").strip()

        if not redirect_url:
            return ToolResult(content="redirect_url is required", is_error=True)

        if service == "spotify":
            result = complete_auth(redirect_url, agent_dir)
            return ToolResult(content=result, is_error=result.startswith("Error"))

        return ToolResult(content=f"OAuth not supported for: {service}", is_error=True)

    async def handle_verify(args: dict[str, Any]) -> ToolResult:
        """Verify a service connection is working."""
        service = args.get("service", "").strip().lower()

        if service == "spotify":
            result = verify_connection(agent_dir)
            return ToolResult(content=result)

        if service == "youtube":
            result = youtube_verify_connection()
            return ToolResult(content=result)

        return ToolResult(content=f"Verify not supported for: {service}", is_error=True)

    return [
        Tool(
            name="onboarding_status",
            description=(
                "Check the setup/onboarding status of a service integration. "
                "Shows which credentials are configured and what steps remain. "
                "Call without a service name to see all services."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Service name (e.g. 'spotify'). Omit to see all.",
                    },
                },
            },
            handler=handle_status,
        ),
        Tool(
            name="onboarding_auth_url",
            description=(
                "Generate an OAuth authorization URL for a service. "
                "Send this URL to the user so they can approve access in their browser."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "Service name (e.g. 'spotify')"},
                },
                "required": ["service"],
            },
            handler=handle_auth_url,
        ),
        Tool(
            name="onboarding_complete_auth",
            description=(
                "Complete an OAuth flow. The user visits the auth URL, approves access, "
                "and gets redirected. They paste the redirect URL here to finish setup."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "Service name (e.g. 'spotify')"},
                    "redirect_url": {"type": "string", "description": "The full redirect URL the user was sent to after approving"},
                },
                "required": ["service", "redirect_url"],
            },
            handler=handle_complete_auth,
        ),
        Tool(
            name="onboarding_verify",
            description=(
                "Verify that a service integration is working correctly. "
                "Tests the connection and returns the current auth status."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "Service name (e.g. 'spotify')"},
                },
                "required": ["service"],
            },
            handler=handle_verify,
        ),
    ]
