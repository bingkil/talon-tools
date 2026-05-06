"""
Unified credentials manager for talon-tools.

Lookup order (first match wins):
    1. File store (loaded from .env or .yaml depending on backend)
    2. Environment variables (always checked as fallback)

Storage backends (set via configure_storage):
    "env"   — .env file (KEY=value dotenv format). Default. Cross-platform.
    "yaml"  — credentials.yaml (flat or nested service groups).
    Custom path — format inferred from extension (.env → dotenv, .yaml/.yml → YAML).

Usage:
    from talon_tools.credentials import get, set_credential, configure_storage

    # Caller (e.g. talon) configures where creds live:
    configure_storage("env", path="/path/to/project/.env")

    # Tools read:
    url = get("JIRA_URL")
    token = get("NOTION_TOKEN", "")

    # Onboarding writes:
    set_credential("JIRA_URL", "https://yourcompany.atlassian.net")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Literal

_MISSING = object()
_Backend = Callable[[str, Any], str]

# In-memory store (populated from file)
_store: dict[str, str] = {}
# Custom programmatic backend
_custom: _Backend | None = None
# Active storage file path and format
_storage_path: Path | None = None
_storage_format: Literal["env", "yaml"] = "env"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def configure_storage(
    backend: Literal["env", "yaml"] | str = "env",
    path: str | Path | None = None,
) -> None:
    """Configure where credentials are stored and read from.

    Args:
        backend: "env" for dotenv format, "yaml" for YAML format.
                 If a file path string ending in .yaml/.yml is passed,
                 auto-detects as yaml. Otherwise treated as "env".
        path: Path to the credentials file. If None, auto-discovers:
              - env: looks for .env in cwd, then creates if needed
              - yaml: looks for credentials.yaml in cwd
    """
    global _storage_path, _storage_format

    # If backend is a path string (not "env"/"yaml"), infer format from extension
    if backend not in ("env", "yaml"):
        path = backend
        backend = "yaml" if str(path).endswith((".yaml", ".yml")) else "env"

    _storage_format = backend  # type: ignore[assignment]

    if path:
        _storage_path = Path(path)
    else:
        _storage_path = None  # will auto-discover on first use

    # Load existing file if it exists
    resolved = _resolve_path()
    if resolved.is_file():
        _load_from_file(resolved)


def configure(backend: dict | _Backend | None) -> None:
    """Set a custom programmatic credentials backend.

    Args:
        backend: dict of key-value pairs, callable(key, default) -> str, or None to clear.
    """
    global _custom
    if backend is None:
        _custom = None
    elif isinstance(backend, dict):
        store = {k.upper(): str(v) for k, v in backend.items()}
        _custom = lambda key, default, _s=store: _s.get(key, default)
    elif callable(backend):
        _custom = backend
    else:
        raise TypeError(f"Expected dict, callable, or None — got {type(backend).__name__}")


def reset() -> None:
    """Clear all state. Falls back to env vars only."""
    global _custom, _storage_path, _storage_format
    _store.clear()
    _custom = None
    _storage_path = None
    _storage_format = "env"


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get(key: str, default: Any = _MISSING) -> str:
    """Get a credential value.

    Lookup order: file store → custom backend → env var.

    Args:
        key: Credential name (e.g. "JIRA_URL", "NOTION_TOKEN").
        default: Value to return if not found. If omitted, raises KeyError.
    """
    ukey = key.upper()

    # 1. File store (loaded from .env or .yaml)
    if ukey in _store:
        return _store[ukey]

    # 2. Custom backend
    if _custom is not None:
        val = _custom(ukey, _MISSING)
        if val is not _MISSING:
            return val

    # 3. Environment variable
    env_val = os.environ.get(key) or os.environ.get(ukey)
    if env_val is not None:
        return env_val

    if default is not _MISSING:
        return default
    raise KeyError(f"Credential '{key}' not found. Set via .env, credentials.yaml, env var, or configure().")


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def set_credential(key: str, value: str) -> None:
    """Set a credential and persist to the configured storage file.

    Also sets in os.environ so it's available immediately in the current process.
    """
    ukey = key.upper()
    _store[ukey] = value
    os.environ[ukey] = value

    # Persist to file
    target = _resolve_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if _storage_format == "yaml":
        _write_yaml(target, ukey, value)
    else:
        _write_env(target, ukey, value)


# ---------------------------------------------------------------------------
# Compatibility — load_yaml / save_yaml (kept for existing callers)
# ---------------------------------------------------------------------------

def load_yaml(path: str | Path = "credentials.yaml") -> None:
    """Load credentials from a YAML file. Switches storage to yaml mode."""
    configure_storage("yaml", path=path)


def save_yaml(path: str | Path | None = None) -> None:
    """Save the current in-memory store to a YAML file."""
    import yaml

    target = Path(path) if path else _resolve_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if target.exists():
        existing = yaml.safe_load(target.read_text(encoding="utf-8")) or {}

    for k, v in _store.items():
        existing[k] = v

    target.write_text(yaml.dump(existing, default_flow_style=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_path() -> Path:
    """Resolve the storage file path."""
    if _storage_path:
        return _storage_path
    if _storage_format == "yaml":
        return Path.cwd() / "credentials.yaml"
    return Path.cwd() / ".env"


def _load_from_file(path: Path) -> None:
    """Load credentials from file into in-memory store."""
    _store.clear()
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        _load_yaml_file(path)
    else:
        _load_env_file(path)


def _load_env_file(path: Path) -> None:
    """Parse a .env file into the store."""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().upper()
        # Strip surrounding quotes
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        _store[key] = value


def _load_yaml_file(path: Path) -> None:
    """Parse a YAML file into the store."""
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _store.update(_flatten_yaml(data))


def _flatten_yaml(data: dict) -> dict[str, str]:
    """Flatten nested YAML into ENV_VAR-style keys.

    jira:
      url: https://...       → JIRA_URL
      api_token: sk-...      → JIRA_API_TOKEN

    Flat keys are kept as-is:
      NOTION_TOKEN: secret   → NOTION_TOKEN
    """
    flat: dict[str, str] = {}
    for key, val in data.items():
        if isinstance(val, dict):
            for child_key, child_val in val.items():
                env_key = f"{key}_{child_key}".upper()
                flat[env_key] = str(child_val)
        else:
            flat[key.upper()] = str(val)
    return flat


def _write_env(path: Path, key: str, value: str) -> None:
    """Write or update a key in a .env file."""
    lines: list[str] = []
    found = False

    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                line_key = stripped.partition("=")[0].strip().upper()
                if line_key == key:
                    # Quote value if it contains spaces or special chars
                    lines.append(f"{key}={_quote_env_value(value)}")
                    found = True
                    continue
            lines.append(line)

    if not found:
        lines.append(f"{key}={_quote_env_value(value)}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _quote_env_value(value: str) -> str:
    """Quote a value for .env if it contains spaces or special characters."""
    if not value:
        return '""'
    needs_quote = any(c in value for c in (" ", "#", "'", '"', "\n", "\t", "="))
    if needs_quote:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _write_yaml(path: Path, key: str, value: str) -> None:
    """Write or update a key in a YAML file."""
    import yaml

    existing: dict = {}
    if path.exists():
        existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    existing[key] = value
    path.write_text(yaml.dump(existing, default_flow_style=False), encoding="utf-8")
