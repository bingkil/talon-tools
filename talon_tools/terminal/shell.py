"""Run shell commands on the host machine (restricted)."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from pathlib import Path

log = logging.getLogger(__name__)

TIMEOUT = 60  # seconds

# Use pwsh (PowerShell 7) on Windows, sh on Unix
if sys.platform == "win32":
    _SHELL = "pwsh.exe"
else:
    _SHELL = None

# ---------------------------------------------------------------------------
# Command blocklist — patterns that should never be executed by an agent.
# Matched case-insensitively against the raw command string.
# ---------------------------------------------------------------------------
_BLOCKED_PATTERNS: list[re.Pattern] = [
    # Destructive file operations
    re.compile(r"\bRemove-Item\b.*-Recurse", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
    re.compile(r"\brmdir\b.*(/s|/q)", re.IGNORECASE),
    re.compile(r"\bdel\s+/[sfq]", re.IGNORECASE),
    re.compile(r"\bFormat-Volume\b", re.IGNORECASE),
    # Disk / partition
    re.compile(r"\bClear-Disk\b", re.IGNORECASE),
    re.compile(r"\bInitialize-Disk\b", re.IGNORECASE),
    # Process / service control
    re.compile(r"\bStop-Process\b", re.IGNORECASE),
    re.compile(r"\bStop-Service\b", re.IGNORECASE),
    re.compile(r"\bRestart-Computer\b", re.IGNORECASE),
    re.compile(r"\bStop-Computer\b", re.IGNORECASE),
    re.compile(r"\bshutdown\b", re.IGNORECASE),
    re.compile(r"\btaskkill\b", re.IGNORECASE),
    # User / credential manipulation
    re.compile(r"\bnet\s+user\b", re.IGNORECASE),
    re.compile(r"\bnet\s+localgroup\b", re.IGNORECASE),
    re.compile(r"\bNew-LocalUser\b", re.IGNORECASE),
    re.compile(r"\bAdd-LocalGroupMember\b", re.IGNORECASE),
    # Registry
    re.compile(r"\bSet-ItemProperty\b.*\bHK", re.IGNORECASE),
    re.compile(r"\bNew-ItemProperty\b.*\bHK", re.IGNORECASE),
    re.compile(r"\breg\s+(add|delete)\b", re.IGNORECASE),
    # Execution policy / security bypass
    re.compile(r"\bSet-ExecutionPolicy\b", re.IGNORECASE),
    re.compile(r"\b-ExecutionPolicy\s+Bypass\b", re.IGNORECASE),
    # Network exfiltration
    re.compile(r"\bInvoke-WebRequest\b.*-OutFile\b", re.IGNORECASE),
    re.compile(r"\bcurl\b.*-o\b", re.IGNORECASE),
    re.compile(r"\bwget\b", re.IGNORECASE),
    # Encoded / obfuscated commands
    re.compile(r"-EncodedCommand\b", re.IGNORECASE),
    re.compile(r"-enc\s+", re.IGNORECASE),
    # Scheduled tasks manipulation
    re.compile(r"\bRegister-ScheduledTask\b", re.IGNORECASE),
    re.compile(r"\bUnregister-ScheduledTask\b", re.IGNORECASE),
    re.compile(r"\bschtasks\s+/(create|delete)\b", re.IGNORECASE),
]


def check_blocked(command: str) -> str | None:
    """Return a reason string if the command is blocked, else None."""
    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(command):
            return f"Blocked: command matches restricted pattern ({pattern.pattern})"
    return None


# ---------------------------------------------------------------------------
# Sensitive paths — never writable regardless of cwd scope.
# ---------------------------------------------------------------------------
_SENSITIVE_PATHS: list[str] = [
    ".env",
    ".ssh",
    ".aws",
    ".gnupg",
    ".config/gcloud",
    "credentials.yaml",
]


def _is_sensitive(path_str: str) -> bool:
    """Check if a path targets a sensitive location."""
    normalized = path_str.replace("\\", "/").lower()
    for s in _SENSITIVE_PATHS:
        if s in normalized:
            return True
    return False


# ---------------------------------------------------------------------------
# Write-scope validation — block writes outside the agent's workspace.
# ---------------------------------------------------------------------------

# Patterns that indicate write intent + capture the target path.
_WRITE_PATTERNS: list[re.Pattern] = [
    # Redirection: > file, >> file
    re.compile(r">>?\s+[\"']?([^\s\"'|;]+)", re.IGNORECASE),
    # Out-File -FilePath / -Path / positional
    re.compile(r"\bOut-File\s+(?:-(?:FilePath|Path)\s+)?[\"']?([^\s\"'|;]+)", re.IGNORECASE),
    # Set-Content / Add-Content -Path
    re.compile(r"\b(?:Set|Add)-Content\s+(?:-Path\s+)?[\"']?([^\s\"'|;]+)", re.IGNORECASE),
    # New-Item -Path
    re.compile(r"\bNew-Item\s+(?:-(?:Path|Name)\s+)?[\"']?([^\s\"'|;]+)", re.IGNORECASE),
    # mkdir / md
    re.compile(r"\b(?:mkdir|md)\s+[\"']?([^\s\"'|;]+)", re.IGNORECASE),
    # Tee-Object -FilePath
    re.compile(r"\bTee-Object\s+(?:-FilePath\s+)?[\"']?([^\s\"'|;]+)", re.IGNORECASE),
    # Python/Node writing to files (common agent pattern)
    re.compile(r"open\([\"']([^\s\"']+)[\"']\s*,\s*[\"'][wa]", re.IGNORECASE),
]


def check_write_scope(command: str, cwd: Path | None) -> str | None:
    """Block commands that write outside the allowed workspace.

    Returns a reason string if blocked, else None.
    Only enforced when cwd is set (i.e., scope is defined).
    """
    if cwd is None:
        return None

    allowed = cwd.resolve()

    for pattern in _WRITE_PATTERNS:
        for match in pattern.finditer(command):
            target_str = match.group(1)
            if not target_str or target_str.startswith("$") or target_str.startswith("("):
                # Skip variable/expression targets — can't resolve statically
                continue

            # Sensitive path check (absolute match regardless of scope)
            if _is_sensitive(target_str):
                return f"Blocked: write targets sensitive path ({target_str})"

            # Resolve relative to cwd
            target = Path(target_str)
            if not target.is_absolute():
                target = cwd / target

            try:
                resolved = target.resolve()
            except (OSError, ValueError):
                continue

            # Check if resolved path is within the allowed directory
            try:
                resolved.relative_to(allowed)
            except ValueError:
                return (
                    f"Blocked: write target '{target_str}' resolves outside workspace "
                    f"({resolved} is not under {allowed})"
                )

    return None


async def run_command(
    command: str,
    *,
    timeout: int = TIMEOUT,
    cwd: Path | None = None,
) -> str:
    """Execute a shell command and return combined stdout+stderr.

    Args:
        command: The shell command to run.
        timeout: Max seconds to wait before killing.
        cwd: Working directory (locked by the tool layer).
    """
    blocked = check_blocked(command)
    if blocked:
        log.warning("BLOCKED command: %s — %s", command[:200], blocked)
        return blocked

    scope_blocked = check_write_scope(command, cwd)
    if scope_blocked:
        log.warning("SCOPE BLOCKED command: %s — %s", command[:200], scope_blocked)
        return scope_blocked

    log.info("EXEC [cwd=%s]: %s", cwd or "(default)", command[:200])

    kwargs: dict = dict(
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    if cwd:
        kwargs["cwd"] = str(cwd)

    if _SHELL:
        proc = await asyncio.create_subprocess_exec(
            _SHELL, "-NoProfile", "-Command", command,
            **kwargs,
        )
    else:
        proc = await asyncio.create_subprocess_shell(
            command,
            **kwargs,
        )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return f"[timed out after {timeout}s]"

    output = stdout.decode(errors="replace").strip()
    # Cap output to avoid blowing up LLM context
    if len(output) > 8000:
        output = output[:4000] + "\n\n... [truncated] ...\n\n" + output[-4000:]
    return output if output else "(no output)"
