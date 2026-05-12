"""
CLI entrypoint for talon_tools.onboarding.

Usage:
    python -m talon_tools.onboarding                     # list services
    python -m talon_tools.onboarding google              # onboard google
    python -m talon_tools.onboarding google --flock /path # per-flock
    python -m talon_tools.onboarding google --agent mark --flock /path
    python -m talon_tools.onboarding --status            # check all services
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .registry import get_all_onboardings
from .runner import run_onboarding


def _print_services(services: dict) -> None:
    """List available services grouped by category."""
    by_cat: dict[str, list] = {}
    for name, ob in sorted(services.items()):
        cat = ob.category or "other"
        by_cat.setdefault(cat, []).append((name, ob))

    print("Available services:\n")
    for cat in sorted(by_cat):
        print(f"  {cat}:")
        for name, ob in by_cat[cat]:
            configured = "✓" if ob.is_configured() else "✗"
            print(f"    {configured} {name:<16} {ob.display_name}")
        print()


def _print_status(services: dict) -> None:
    """Show configuration status for all services."""
    print("Service status:\n")
    for name, ob in sorted(services.items()):
        status = "configured" if ob.is_configured() else "not configured"
        symbol = "✓" if ob.is_configured() else "✗"
        print(f"  {symbol} {name:<16} {status}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="talon-auth",
        description="Authenticate and configure services for Talon agents",
    )
    parser.add_argument(
        "service",
        nargs="?",
        help="Service to configure (e.g. google, telegram, spotify)",
    )
    parser.add_argument(
        "--flock",
        help="Path to the flock directory",
    )
    parser.add_argument(
        "--agent",
        help="Agent name for per-agent credentials (e.g. --agent mark)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show configuration status for all services",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_services",
        help="List available services",
    )

    args = parser.parse_args()
    services = get_all_onboardings()

    if args.status:
        _print_status(services)
        return

    if args.list_services or not args.service:
        _print_services(services)
        if not args.service:
            print("Usage: talon auth <service> [--agent <name>] [--flock <path>]")
        return

    # Resolve flock directory
    flock_dir = Path(args.flock).resolve() if args.flock else None

    # For per-agent Google auth, delegate to the Google auth module directly
    if args.service == "google" and args.agent:
        from talon_tools.google.auth import authorize_interactive
        if not flock_dir:
            print("Error: --flock is required when using --agent")
            sys.exit(1)
        target = flock_dir / args.agent / "google" / "token.json"
        print(f"Authorizing Google for agent: {args.agent}")
        print(f"Flock: {flock_dir}")
        print(f"Token will be saved to: {target}")
        authorize_interactive(target)
        return

    # Run the onboarding flow
    result = run_onboarding(args.service, flock_dir=flock_dir)
    if result["status"] == "error":
        sys.exit(1)
    elif result["status"] == "cancelled":
        sys.exit(130)


if __name__ == "__main__":
    main()
