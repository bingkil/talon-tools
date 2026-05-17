---
description: Read, write, search, and manage files in a sandboxed workspace directory
dependencies:
---

# Workspace

Secure file system operations sandboxed to a workspace root directory. Read, write, search, append, update sections, list, and delete files without risk of escaping the sandbox.

## When to Use

- "Save this to a file"
- "Read the contents of..."
- "List files in the workspace"
- "Delete that file"
- "Create a new file with..."
- "Add this to the end of my notes"
- "Update the summary section of that doc"
- "Search my workspace for anything about MCP"
- Agent-managed file storage and retrieval

## Installation & Invocation

```bash
pip install talon-tools
```

No extra dependencies — uses Python stdlib only. No credentials required.

Load and call (requires a `root_dir` for sandboxing):

```python
import asyncio
from pathlib import Path
from talon_tools.workspace.tools import build_tools

tools = {t.name: t for t in build_tools(root_dir=Path("./workspace"))}

# List files
result = asyncio.run(tools["ws_list"].handler({}))
print(result.content)

# Write a file
result = asyncio.run(tools["ws_write"].handler({"path": "notes.md", "content": "# My Notes"}))
print(result.content)
```

### Without Python

This tool just wraps basic file operations — if your agent already has file system access (VS Code Copilot, Claude Code, Cursor, etc.), you don't need this package. Use native file read/write/list/delete commands directly.

## Available Tools

| Tool | Purpose |
|------|---------|
| `ws_read` | Read a file from the workspace |
| `ws_write` | Create or overwrite a file (auto-creates directories) |
| `ws_append` | Append content to a file without overwriting (creates if missing) |
| `ws_update` | Upsert a named Markdown section — replace if exists, append if not |
| `ws_grep` | Search for text across all workspace files (substring or regex) |
| `ws_list` | List directory contents |
| `ws_delete` | Delete a file or directory |

## Notes

- No dependencies — uses Python stdlib
- All paths are relative to the workspace root
- Cannot escape the sandbox via `../` traversal
- Directories are created automatically when writing files
- `ws_grep` only searches text file extensions (.md, .txt, .py, .yaml, .json, .toml, .html, .csv)
- `ws_update` matches section headings at configurable levels (##, ###, etc.)
