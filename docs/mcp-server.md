# MCP Server

Expose talon-tools to any MCP-compatible IDE (VS Code Copilot, Cursor, Windsurf, JetBrains) as an MCP stdio server.

## Architecture

```
IDE (VS Code / Cursor / Windsurf / JetBrains)
    │  JSON-RPC over stdio
    ▼
talon-tools MCP server (talon_tools/mcp_server.py)
    │  uses build_tools() + credential contract
    ▼
Service APIs (Jira, Google, Jenkins, Spotify, etc.)
```

The server dynamically discovers tool modules at startup, calls each module's `build_tools()` function, and registers the resulting tools with the MCP protocol. Existing tool code doesn't change — the same `credentials.get()`, `validate()`, and handler functions work identically.

### Components

| File | Purpose |
|------|---------|
| `talon_tools/mcp_server.py` | MCP server — discovery, registration, stdio transport |
| `talon_tools/cli.py` | CLI entry point — `talon-tools mcp` subcommand |
| `talon_tools/credentials.py` | Credential contract — provider protocol, `get`/`set`/`validate` |
| `talon_tools/onboarding/` | Per-module setup definitions and `is_configured()` checks |

### Server internals

1. **Credential init** — resolves the credentials file using `_resolve_creds_path()` (same logic as `setup --status`)
2. **Tool discovery** — scans `talon_tools/*/tools.py`, imports each, calls `build_tools()` with synthetic defaults for required params
3. **Registration** — registers tools via `@server.list_tools()` and `@server.call_tool()` handlers
4. **Resource** — exposes `talon-tools://credentials/status` showing configured vs missing credentials
5. **Transport** — runs over stdio using the official `mcp` SDK's `stdio_server()`

Modules that fail to import (missing optional deps) are silently skipped.

---

## CLI

```
talon-tools mcp [--tools MODULE,...] [--creds PATH]
```

| Flag | Description |
|------|-------------|
| `--tools` | Comma-separated list of modules to load (e.g. `atlassian,google,jenkins`). Omit to load all. |
| `--creds` | Path to credentials file (`.env` or `.yaml`). Overrides auto-detection. |

### Other CLI commands

```bash
talon-tools setup              # Interactive credential setup wizard
talon-tools setup --status     # Show which modules are configured
talon-tools setup --tool NAME  # Set up a specific module
talon-tools tools              # List all available tool modules and their tools
talon-tools tools MODULE       # Inspect a specific module
```

---

## Credentials

### Resolution order

The MCP server resolves credentials in the same order as `talon-tools setup`:

1. **`--creds` flag** (explicit path)
2. **`TALON_TOOLS_CREDENTIALS` env var**
3. **Existing file discovery:**
   - `$CWD/.env`
   - `$CWD/credentials.yaml`
   - `~/.config/talon-tools/credentials.yaml`
   - `~/.config/talon/credentials.yaml`
4. **Default:** `~/.talon-tools/credentials.yaml`

### Supported formats

**YAML** (`.yaml` / `.yml`):
```yaml
JIRA_URL: https://company.atlassian.net
JIRA_USERNAME: you@company.com
JIRA_API_TOKEN: your-api-token
JENKINS_URL: https://jenkins.company.com
JENKINS_USERNAME: admin
JENKINS_API_TOKEN: your-token
```

**.env**:
```env
JIRA_URL=https://company.atlassian.net
JIRA_USERNAME=you@company.com
JIRA_API_TOKEN=your-api-token
```

### Fallback to environment variables

The credential provider always checks environment variables as a fallback. If a key isn't in the file, the corresponding env var is used. This means IDE `env` / `envFile` settings work without any file on disk.

### Token refresh

OAuth tokens (Google, Spotify, Microsoft) are refreshed automatically. When a handler calls `credentials.set_credential(key, value)`, the provider persists the new value atomically (write to temp file + rename).

### First-time setup

```bash
# Interactive — prompts for all missing credentials
uv run talon-tools setup

# Single module
uv run talon-tools setup --tool atlassian

# Check what's configured
uv run talon-tools setup --status
```

---

## Running the server

### Direct (terminal)

```bash
# All modules (requires all optional deps)
uv run --extra all talon-tools mcp

# Specific modules only
uv run --extra mcp --extra atlassian --extra jenkins talon-tools mcp --tools atlassian,jenkins

# With explicit credentials
uv run --extra all talon-tools mcp --creds ~/.talon-tools/credentials.yaml
```

### Startup output (stderr)

```
Talon Tools MCP Server starting...
  Credentials: C:\Users\you\.config\talon-tools\credentials.yaml
  Modules: 12 loaded
  Ready: atlassian, earthquake, jenkins, notion, search, terminal, weather, workspace
  Unavailable (missing creds): discord, google, servicenow, slack
  Tools: 67 total
  Transport: stdio
  Ready.
```

---

## IDE Configuration

### VS Code (Copilot / GitHub Copilot Chat)

Add to `.vscode/mcp.json` (workspace) or User Settings JSON:

**All tools:**
```json
{
  "servers": {
    "talon-tools": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--extra", "all", "talon-tools", "mcp"],
      "cwd": "/path/to/talon-tools-oss"
    }
  }
}
```

**Selective tools (recommended — smaller context for the LLM):**
```json
{
  "servers": {
    "talon-tools": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--extra", "mcp", "--extra", "atlassian", "--extra", "jenkins", "talon-tools", "mcp", "--tools", "atlassian,jenkins"],
      "cwd": "/path/to/talon-tools-oss"
    }
  }
}
```

**With env var overrides:**
```json
{
  "servers": {
    "talon-tools": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--extra", "all", "talon-tools", "mcp"],
      "cwd": "/path/to/talon-tools-oss",
      "env": {
        "JIRA_URL": "https://company.atlassian.net",
        "JIRA_USERNAME": "you@company.com",
        "JIRA_API_TOKEN": "your-token"
      }
    }
  }
}
```

**With envFile:**
```json
{
  "servers": {
    "talon-tools": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--extra", "all", "talon-tools", "mcp"],
      "cwd": "/path/to/talon-tools-oss",
      "envFile": "${workspaceFolder}/.env"
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "talon-tools": {
      "command": "uv",
      "args": ["run", "--extra", "all", "talon-tools", "mcp"],
      "cwd": "/path/to/talon-tools-oss"
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "talon-tools": {
      "command": "uv",
      "args": ["run", "--extra", "all", "talon-tools", "mcp"],
      "cwd": "/path/to/talon-tools-oss"
    }
  }
}
```

---

## Optional dependencies

Each tool module has its own optional dependency group. The `mcp` extra provides the server SDK; module extras provide their API clients:

| Extra | Provides |
|-------|----------|
| `mcp` | MCP SDK (`mcp>=1.0`, `httpx`) |
| `atlassian` | `atlassian-python-api` |
| `google` | Google API client libraries |
| `jenkins` | `httpx` |
| `notion` | `notion-client` |
| `spotify` | `httpx` |
| `servicenow` | `aiohttp`, `beautifulsoup4` |
| `docreader` | `pypdf`, `openpyxl`, `python-docx`, `python-pptx` |
| `x` | `httpx`, `browser-cookie3` |
| `facebook` | `playwright`, `browser-cookie3` |
| `all` | Everything above |

Use `--extra all` to install everything, or cherry-pick specific extras to keep the environment lean.

---

## MCP Resources

The server exposes one resource:

| URI | Description |
|-----|-------------|
| `talon-tools://credentials/status` | JSON showing which tools have credentials configured and which are missing |

Example response:
```json
{
  "configured": ["atlassian", "jenkins", "notion"],
  "missing": {
    "google": ["GOOGLE_CREDENTIALS_FILE"],
    "slack": ["SLACK_BOT_TOKEN"]
  }
}
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Module shows 0 tools | Missing optional dependency | Add the module's extra: `--extra atlassian` |
| "Unavailable (missing creds)" | Credentials file not found or key missing | Run `talon-tools setup --status` to check; run `setup --tool NAME` to configure |
| Server doesn't start | `mcp` extra not installed | Use `--extra mcp` (or `--extra all`) |
| VS Code shows stderr as warnings | Normal — stderr is the banner output | Informational only; not an error |
| Tools not appearing in IDE | Server not registered or wrong `cwd` | Check `mcp.json` path; ensure `cwd` points to the repo root |

Install: `pip install talon-tools[mcp]` or `uvx --from talon-tools[all,mcp] talon-tools mcp`

## OAuth in MCP Context

OAuth flows (Google, Spotify, Microsoft) require a one-time browser auth. The `setup` command handles this:

```bash
uvx talon-tools setup --tool google
# Opens browser for OAuth consent
# Stores refresh token in credentials.yaml via set_credential()
```

Subsequent MCP calls use the stored refresh token. When it expires, `set_credential()` writes the refreshed token back to the YAML file automatically.

## Tool Discovery

The MCP server uses native MCP tool listing. Tools that fail `validate()` (missing credentials) are not registered — the IDE only sees tools the user has configured.

Additionally, the server exposes a `credentials/status` MCP resource:
```json
{
  "configured": ["atlassian", "google", "jenkins"],
  "missing": {
    "spotify": ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"],
    "notion": ["NOTION_TOKEN"]
  }
}
```

The agent can read this resource to guide users toward setting up additional tools.

## Security Notes

- `credentials.yaml` should be `chmod 600` / ACL-restricted (the provider enforces this on write)
- Never log credential values
- The YAML file path should not be inside a git repo (default `~/.talon-tools/` is safe)
- OAuth tokens in the YAML are refresh tokens — short-lived access tokens are never persisted
- `YamlFileProvider.set()` uses atomic write (tmp + rename) to prevent corruption
- Use VS Code `${input:...}` password prompts instead of hardcoding tokens in `mcp.json`

## Implementation Plan

| Step | Files | Notes |
|------|-------|-------|
| 1. `YamlFileProvider` | `talon_tools/providers/yaml_file.py` | Atomic writes, chmod enforcement |
| 2. MCP server entry point | `talon_tools/mcp_server.py` | Tool schema translation, `--tools` filter, `credentials/status` resource |
| 3. CLI `mcp` + `setup` commands | `talon_tools/cli.py` | Interactive prompts, OAuth orchestration, `--tool` filter |
| 4. Script entry point | `pyproject.toml` | `[project.scripts]` entry |
| 5. Docs: IDE config examples | This file + README | Per-IDE config snippets |

## Distribution

```toml
# pyproject.toml additions
[project.scripts]
talon-tools = "talon_tools.cli:main"

[project.optional-dependencies]
mcp = ["mcp>=1.0"]
```

Install: `pip install talon-tools[mcp]` or run directly via `uvx --from talon-tools[all,mcp] talon-tools mcp`
