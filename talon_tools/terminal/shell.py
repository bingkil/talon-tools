"""Run shell commands on the host machine (restricted)."""

from __future__ import annotations

import asyncio
import logging
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
