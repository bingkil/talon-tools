---
description: Execute shell commands with timeout and security controls
dependencies:
---

# Terminal

Execute shell commands and return output. Runs in PowerShell on Windows or sh on Unix, with timeout enforcement and destructive command blocking.

## When to Use

- "Run this command..."
- "Check disk space"
- "What's my IP address?"
- "List files in this directory"
- "Install this package"
- System administration tasks
- Running scripts or CLI tools

## Installation & Invocation

```bash
pip install talon-tools
```

No extra dependencies — uses Python stdlib only. No credentials required.

Load and call:

```python
import asyncio
from talon_tools.terminal.tools import build_tools

tools = {t.name: t for t in build_tools()}
result = asyncio.run(tools["terminal"].handler({"command": "echo hello"}))
print(result.content)
```

### Without Python

This tool just runs shell commands — if your agent already has terminal/shell access (VS Code Copilot, Claude Code, Cursor, etc.), you don't need this package at all. Just run commands directly in the terminal.

## Available Tools

| Tool | Purpose |
|------|---------|
| `terminal` | Run a shell command and return stdout |

## Parameters

- `command` — Shell command to execute (required)
- `timeout` — Max execution time in seconds (default 60, max 120)

## Notes

- No dependencies — uses Python stdlib
- Platform-aware: PowerShell on Windows, sh on Unix
- Destructive commands are blocked (e.g., `rm -rf /`, registry edits, `Stop-Process`)
- Max timeout: 120 seconds
- Optional working directory sandboxing when configured
