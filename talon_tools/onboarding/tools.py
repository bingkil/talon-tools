"""Onboarding tool definitions for LLM agents.

Service-specific onboarding modules are discovered via the registry
in onboarding/registry.py — no explicit imports here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from talon_tools import Tool, ToolResult

from .base import ToolOnboarding
from .registry import get_all_onboardings as get_services


def build_tools(agent_dir: Path | None = None) -> list[Tool]:
    """Return onboarding tools."""

    async def handle_status(args: dict[str, Any]) -> ToolResult:
        """Check onboarding status for a service or all services."""
        services = get_services()
        service = args.get("service", "").strip().lower()

        if service:
            ob = services.get(service)
            if not ob:
                available = ", ".join(services.keys())
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
        for name, ob in services.items():
            icon = "✓" if ob.is_configured() else "✗"
            lines.append(f"  {icon} {ob.display_name}")
        if not services:
            lines.append("  (no onboarding modules registered)")
        return ToolResult(content="\n".join(lines))

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
                        "description": "Service name. Omit to see all.",
                    },
                },
            },
            handler=handle_status,
        ),
    ]
