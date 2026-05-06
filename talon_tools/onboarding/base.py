"""Base types for tool onboarding."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from talon_tools.credentials import get as cred


@dataclass
class OnboardingStep:
    """A single step in the onboarding flow."""
    title: str
    instruction: str
    credential_key: str | None = None  # key to check/save (e.g. "SPOTIFY_CLIENT_ID")
    is_url: bool = False  # if True, the step produces a URL for the user to visit
    is_command: bool = False  # if True, run a subprocess command
    command: list[str] | None = None  # e.g. ["wacli", "auth"]
    is_optional: bool = False
    oauth_handler: Callable[..., None] | None = None  # callable that runs the full OAuth flow


@dataclass
class ToolOnboarding:
    """Defines onboarding for a tool."""
    service: str
    display_name: str
    setup_type: str = "manual"  # "manual" | "oauth" | "qr" | "zero"
    category: str = "tool"  # "tool" | "channel"
    dependencies: list[str] = field(default_factory=list)  # binary names from installer registry
    pip_extras: list[str] = field(default_factory=list)  # pip extras to install, e.g. ["google"]
    steps: list[OnboardingStep] = field(default_factory=list)
    verify: Callable[[], str] | None = None  # post-setup verification

    def status(self) -> dict:
        """Check which credentials are configured."""
        results: dict[str, bool] = {}
        for step in self.steps:
            if step.credential_key:
                results[step.credential_key] = check_credential(step.credential_key)
        return results

    def is_configured(self) -> bool:
        """True if all required credentials are set."""
        for step in self.steps:
            if step.credential_key and not step.is_optional:
                if not check_credential(step.credential_key):
                    return False
        return True

    def next_step(self) -> OnboardingStep | None:
        """Return the next step that needs action, or None if complete."""
        for step in self.steps:
            if step.credential_key and not check_credential(step.credential_key):
                if not step.is_optional:
                    return step
        return None


# Keep old name as alias for backward compatibility
ServiceOnboarding = ToolOnboarding


def check_credential(key: str) -> bool:
    """Check if a credential is set and non-empty."""
    try:
        val = cred(key, "")
        return bool(val)
    except Exception:
        return False
