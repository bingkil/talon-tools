---
name: chrome-bookmarks
description: Read Chrome bookmarks from the local filesystem (cross-platform)
dependencies: talon-tools
---

# Read Chrome Bookmarks

Read and search Chrome bookmarks from the local filesystem. Works on Windows, macOS, and Linux — auto-detects the correct path based on the OS.

## When to Use

- "Check my Chrome bookmarks"
- "Show me my bookmarks"
- "Search my bookmarks for..."
- "What bookmarks do I have in folder X?"
- "Find the bookmark for..."
- Exporting or listing saved URLs

## Installation & Invocation

```bash
pip install talon-tools
```

No credentials required — reads the local Chrome Bookmarks JSON file.

Load with:

```
get_tool("chrome-bookmarks")
```

## Available Tools

| Tool | Purpose |
|------|---------|
| `read_chrome_bookmarks` | Read and search Chrome bookmarks |

## Parameters

- `username` — OS username (optional, defaults to current user)
- `path` — Explicit path to Bookmarks file (overrides auto-detection)
- `folder` — Filter by folder path (substring match)
- `query` — Search by title or URL (case-insensitive)
- `limit` — Max results to return (default 50)

## Cross-Platform Paths

The tool auto-detects the bookmarks file location:

| OS | Path |
|----|------|
| Windows | `C:\Users\<user>\AppData\Local\Google\Chrome\User Data\Default\Bookmarks` |
| macOS | `/Users/<user>/Library/Application Support/Google/Chrome/Default/Bookmarks` |
| Linux | `/home/<user>/.config/google-chrome/Default/Bookmarks` |

## Notes

- Returns markdown-formatted list of bookmarks with titles, URLs, and folder paths.
- Only reads the Default Chrome profile. For other profiles, use the `path` parameter with the full path.
- No write operations — read-only access to bookmarks.
