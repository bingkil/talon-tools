"""
Credential contract for talon-tools.

talon-tools is a platform-agnostic tool library. It does NOT own credential
storage — it defines the interface that host programs must implement.

Host programs (e.g. Talon, standalone scripts, test harnesses) inject a
CredentialProvider at startup via `init(provider)`. Tools read credentials
through the module-level `get()` function which delegates to the provider.

If no provider is injected, falls back to environment variables only.

Usage (tool code):
    from talon_tools.credentials import get
    url = get("JIRA_URL")

Usage (host program):
    from talon_tools import credentials
    credentials.init(my_provider)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


_MISSING = object()


# ---------------------------------------------------------------------------
# Contract types
# ---------------------------------------------------------------------------

@dataclass
class CredentialRequirement:
    """Declares a credential that a tool needs to function.

    Attributes:
        key: Environment-style key name (e.g. "JIRA_URL").
        description: Human-readable explanation of what this credential is.
        required: If True, the tool cannot function without this.
                  If False, it's optional (degraded functionality without it).
        hint: Optional URL or instruction to help the user obtain this credential.
    """
    key: str
    description: str
    required: bool = True
    hint: str = ""


class MissingCredentialsError(Exception):
    """Raised when a tool is missing required credentials.

    Attributes:
        tool: Name of the tool (e.g. "atlassian", "google").
        missing: List of missing credential requirements.
    """

    def __init__(self, tool: str, missing: list[CredentialRequirement]):
        self.tool = tool
        self.missing = missing
        keys = ", ".join(r.key for r in missing)
        lines = [f"Tool '{tool}' is missing required credentials: {keys}", ""]
        for req in missing:
            line = f"  - {req.key}: {req.description}"
            if req.hint:
                line += f"\n    → {req.hint}"
            lines.append(line)
        super().__init__("\n".join(lines))


@runtime_checkable
class CredentialProvider(Protocol):
    """Interface that host programs implement to supply credentials to tools."""

    def get(self, key: str, default: Any = ...) -> str:
        """Get a credential value by key. Raise KeyError if not found and no default."""
        ...

    def keys(self) -> set[str]:
        """Return all known credential keys (for discovery/enumeration)."""
        ...


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_provider: CredentialProvider | None = None


def init(provider: CredentialProvider) -> None:
    """Inject the credential provider. Called once by the host program at startup.

    Args:
        provider: Any object implementing CredentialProvider protocol.
    """
    global _provider
    _provider = provider


def reset() -> None:
    """Clear the provider. Falls back to env vars only. Useful for testing."""
    global _provider
    _provider = None


def get(key: str, default: Any = _MISSING) -> str:
    """Get a credential value.

    Delegates to the injected provider if available, otherwise falls back
    to environment variables.

    Args:
        key: Credential name (e.g. "JIRA_URL", "NOTION_TOKEN").
        default: Value to return if not found. If omitted, raises KeyError.
    """
    if _provider is not None:
        try:
            return _provider.get(key)
        except KeyError:
            if default is not _MISSING:
                return default
            raise KeyError(f"Credential '{key}' not found and no default provided.")

    # No provider — env var fallback
    ukey = key.upper()
    val = os.environ.get(key) or os.environ.get(ukey)
    if val is not None:
        return val
    if default is not _MISSING:
        return default
    raise KeyError(f"Credential '{key}' not found and no provider configured.")


def keys() -> set[str]:
    """Return all known credential keys from the provider."""
    if _provider is not None:
        return _provider.keys()
    return set()


# ---------------------------------------------------------------------------
# Credential registry (populated by validate() calls)
# ---------------------------------------------------------------------------

_registry: dict[str, list[CredentialRequirement]] = {}


def register(tool: str, requirements: list[CredentialRequirement]) -> None:
    """Register credential requirements for a tool.

    Called automatically by validate(), but can also be called directly
    to register without validation (e.g. at module load time).
    """
    _registry[tool] = requirements


def list_credentials(tool: str | None = None) -> dict[str, list[CredentialRequirement]] | list[CredentialRequirement]:
    """Return credential requirements for onboarding/setup.

    Args:
        tool: If specified, return requirements for that tool only.
              If None, return all registered tools.

    Returns:
        A list of CredentialRequirement if tool is specified,
        or a dict mapping tool name → requirements for all tools.
    """
    if tool:
        return _registry.get(tool, [])
    return dict(_registry)


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------

def validate(tool: str, requirements: list[CredentialRequirement]) -> None:
    """Validate that all required credentials are available.

    Call this in build_tools() before returning tools.
    Also registers the requirements so onboarding can discover them.

    Args:
        tool: Tool name for error messages.
        requirements: List of credential requirements.

    Raises:
        MissingCredentialsError: If any required credential is missing.
    """
    _registry[tool] = requirements
    missing = []
    for req in requirements:
        if not req.required:
            continue
        try:
            val = get(req.key, "")
            if not val:
                missing.append(req)
        except KeyError:
            missing.append(req)
    if missing:
        raise MissingCredentialsError(tool, missing)


# ---------------------------------------------------------------------------
# Backward compatibility — set_credential (used by onboarding code)
# ---------------------------------------------------------------------------

def set_credential(key: str, value: str) -> None:
    """Set a credential. Delegates to provider if it supports writing.

    This is primarily used by onboarding/setup code in the host program.
    Falls back to setting an environment variable.
    """
    if _provider is not None and hasattr(_provider, "set"):
        _provider.set(key, value)  # type: ignore[attr-defined]
    else:
        os.environ[key.upper()] = value
