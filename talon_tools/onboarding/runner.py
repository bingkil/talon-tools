"""
Interactive onboarding runner — walks through setup steps for any service.

Handles:
  - Manual credential entry (API keys, bot tokens)
  - OAuth flows (Google, Spotify)
  - Subprocess commands (signal-cli link)
  - Encrypted credential storage

Usage:
    from talon_tools.onboarding.runner import run_onboarding
    run_onboarding("telegram", flock_dir=Path("/path/to/flock"))
"""

from __future__ import annotations

import getpass
import subprocess
import sys
from pathlib import Path

from talon_tools.credentials import set_credential
from .base import ToolOnboarding, OnboardingStep
from .registry import get_all_onboardings


class _SetupCancelled(Exception):
    """Raised when the user cancels setup."""


def _prompt(msg: str, secret: bool = False) -> str:
    """Prompt for input, raising _SetupCancelled on Ctrl+C."""
    try:
        if secret:
            return getpass.getpass(msg)
        return input(msg)
    except (KeyboardInterrupt, EOFError):
        raise _SetupCancelled()


def run_onboarding(
    service: str,
    flock_dir: Path | None = None,
    skip_configured: bool = True,
) -> dict:
    """Run the interactive onboarding flow for a service.

    Args:
        service: Service name (e.g. "telegram", "google", "spotify").
        flock_dir: Flock directory for per-flock credential storage.
        skip_configured: Skip steps whose credential is already set.

    Returns:
        {"status": "success"|"cancelled"|"error", ...}
    """
    services = get_all_onboardings()
    ob = services.get(service)
    if not ob:
        available = ", ".join(sorted(services.keys()))
        print(f"Unknown service: {service}")
        print(f"Available: {available}")
        return {"status": "error", "error": f"Unknown service: {service}"}

    print()
    print(f"╭─ {ob.display_name} Setup ─{'─' * max(0, 40 - len(ob.display_name))}╮")
    print(f"│ Type: {ob.setup_type:<41}│")
    if ob.category == "channel":
        print(f"│ Category: messaging channel{' ' * 19}│")
    print(f"╰{'─' * 48}╯")

    # Check if already configured
    if skip_configured and ob.is_configured():
        print(f"\n  ✓ {ob.display_name} is already configured.")
        rerun = _prompt("  Reconfigure? [y/N]: ").strip().lower()
        if rerun not in ("y", "yes"):
            return {"status": "already_configured"}

    try:
        return _run_steps(ob, flock_dir)
    except _SetupCancelled:
        print("\n\n  Setup cancelled.")
        return {"status": "cancelled"}


def _run_steps(ob: ToolOnboarding, flock_dir: Path | None) -> dict:
    """Execute each onboarding step interactively."""
    total = len(ob.steps)
    results: dict[str, str] = {}

    for i, step in enumerate(ob.steps, 1):
        print(f"\n[{i}/{total}] {step.title}")
        print()

        # Show instruction
        for line in step.instruction.splitlines():
            print(f"  {line}")
        print()

        # Handle different step types
        if step.oauth_handler:
            _run_oauth_step(step)
        elif step.is_command and step.command:
            _run_command_step(step)
        elif step.credential_key:
            value = _run_credential_step(step)
            if value:
                results[step.credential_key] = value

    # Summary
    print(f"\n✅ {ob.display_name} setup complete!")
    if results:
        print("  Credentials saved:")
        for key in results:
            print(f"    ✓ {key}")

    return {"status": "success", "credentials": list(results.keys())}


def _run_oauth_step(step: OnboardingStep) -> None:
    """Run an OAuth handler (e.g. Google browser flow, signal-cli install)."""
    proceed = _prompt("  Ready to proceed? [Y/n]: ").strip().lower()
    if proceed in ("n", "no"):
        if step.is_optional:
            print("  Skipped.")
            return
        raise _SetupCancelled()

    try:
        step.oauth_handler()  # type: ignore[misc]
    except Exception as e:
        print(f"  ✗ Error: {e}")
        if not step.is_optional:
            raise


def _run_command_step(step: OnboardingStep) -> None:
    """Run a subprocess command (e.g. signal-cli link)."""
    proceed = _prompt("  Ready to run? [Y/n]: ").strip().lower()
    if proceed in ("n", "no"):
        if step.is_optional:
            print("  Skipped.")
            return
        raise _SetupCancelled()

    try:
        result = subprocess.run(
            step.command,  # type: ignore[arg-type]
            capture_output=False,
        )
        if result.returncode != 0:
            print(f"  ⚠ Command exited with code {result.returncode}")
    except FileNotFoundError:
        print(f"  ✗ Command not found: {step.command[0]}")  # type: ignore[index]
        if not step.is_optional:
            raise

    # If this step has a credential_key, prompt for it after
    if step.credential_key:
        value = _prompt(f"  {step.credential_key}: ").strip()
        if value:
            set_credential(step.credential_key, value)


def _run_credential_step(step: OnboardingStep) -> str | None:
    """Prompt for a credential value and save it."""
    # Check if already set
    from .base import check_credential
    if check_credential(step.credential_key):  # type: ignore[arg-type]
        print(f"  ✓ {step.credential_key} is already set.")
        update = _prompt("  Update? [y/N]: ").strip().lower()
        if update not in ("y", "yes"):
            return None

    # Determine if this is a secret value
    key = step.credential_key or ""
    is_secret = any(
        s in key.lower()
        for s in ("token", "secret", "password", "key", "api_token")
    )

    value = _prompt(f"  {key}: ", secret=is_secret).strip()
    if not value:
        if step.is_optional:
            print("  Skipped (optional).")
            return None
        print(f"  ✗ {key} cannot be empty.")
        value = _prompt(f"  {key}: ", secret=is_secret).strip()
        if not value:
            raise _SetupCancelled()

    set_credential(key, value)
    print(f"  ✓ {key} saved.")
    return value
