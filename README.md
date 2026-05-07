<p align="center">
  <img src="talon-tools.png" width="200" alt="talon-tools logo">
</p>

<h1 align="center">talon-tools</h1>

<p align="center">
  <strong>Unified Python toolkit for building AI-powered agents</strong><br>
  Google · Microsoft · Atlassian · Notion · Spotify · X · Facebook · and more
</p>

<p align="center">
  <a href="https://github.com/bingkil/talon-tools/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
</p>

---

## What is this?

**talon-tools** provides a batteries-included set of tool modules for AI agents. Each module wraps a service API and exposes a standard `build_tools() -> list[Tool]` interface that plugs into any LLM agent framework.

Features:
- **Multi-service**: Google Workspace, Microsoft 365, Atlassian, Notion, Spotify, X, Facebook, ServiceNow, web search, file system, terminal
- **Credential management**: Pluggable storage (`.env`, YAML, env vars, custom backends)
- **Interactive onboarding**: `python -m talon_tools.cli setup` walks through OAuth flows, cookie extraction, and credential entry
- **Modular installs**: Only install what you need via pip extras

## Install

```bash
pip install talon-tools          # core only
pip install talon-tools[google]  # with Google integrations
pip install talon-tools[all]     # everything
```

Requires **Python 3.11+**.

## Modules

| Module | Extra | Description |
|--------|-------|-------------|
| `credentials` | *(core)* | Unified credential manager — .env, YAML, or custom backend |
| `atlassian` | `[atlassian]` | Jira & Confluence API client |
| `google` | `[google]` | Gmail, Calendar, Drive, Sheets, Keep, Contacts, Photos, YouTube |
| `microsoft` | `[microsoft]` | Outlook, Teams, Calendar via Microsoft Graph |
| `notion` | `[notion]` | Notion pages & databases |
| `servicenow` | `[servicenow]` | ServiceNow incidents & change requests |
| `facebook` | `[facebook]` | Facebook session-based automation |
| `x` | `[x]` | X (Twitter) API |
| `spotify` | `[spotify]` | Spotify playback & library |
| `search` | `[search]` | Web search via DuckDuckGo |
| `docreader` | `[docreader]` | PDF, Excel, Word, PowerPoint parsing |
| `mcp` | `[mcp]` | Model Context Protocol client |
| `terminal` | *(core)* | Shell command execution |
| `workspace` | *(core)* | File system operations |

## Setup

Interactive setup walks you through credentials for each service:

```bash
python -m talon_tools.cli setup          # all tools
python -m talon_tools.cli setup google   # just Google
python -m talon_tools.cli setup x        # just X
```

Features:
- Automatic OAuth flows (Google, Microsoft, Spotify)
- Browser cookie extraction (X, Facebook)
- Signal: auto-downloads signal-cli + Java to `~/.config/talon/`
- Falls back to manual entry if automation fails
- Configurable credential storage (`.env` or YAML)

## Credentials

```python
from talon_tools.credentials import configure_storage, get, set_credential

# .env file
configure_storage("env", path=".env")

# YAML file
configure_storage("yaml", path="credentials.yaml")

# Custom path (format auto-detected from extension)
configure_storage("/path/to/secrets.env")
```

Lookup order: **file store → environment variables** (env vars always work as fallback/override).

### .env format

```bash
JIRA_URL=https://yourcompany.atlassian.net
JIRA_USERNAME=you@company.com
JIRA_API_TOKEN=your-api-token
NOTION_TOKEN=secret_abc123
```

### YAML format

```yaml
jira:
  url: https://yourcompany.atlassian.net
  username: you@company.com
  api_token: your-api-token

notion:
  token: secret_abc123
```

Nested YAML keys auto-flatten: `jira.url` → `JIRA_URL`.

See [`credentials.yaml.example`](credentials.yaml.example) for all available keys.

## Quick Start

### API client

```python
import asyncio
from talon_tools.atlassian.client import JiraClient
from talon_tools import credentials

credentials.configure_storage("env", path=".env")

async def main():
    jira = JiraClient()
    me = await jira.myself()
    print(f"Logged in as: {me['displayName']}")

    issues = await jira.search("assignee = currentUser()", limit=5)
    for issue in issues["issues"]:
        print(f"  {issue['key']}: {issue['fields']['summary']}")

asyncio.run(main())
```

### Agent tools

Each module exposes `build_tools() -> list[Tool]` — ready for any LLM agent loop:

```python
from talon_tools.atlassian.tools import build_tools as jira_tools
from talon_tools.notion.tools import build_tools as notion_tools

# Collect tools from the modules you need
tools = jira_tools() + notion_tools()

# Tools are async callables: tool.handler({"jql": "..."}) -> ToolResult
for tool in tools:
    print(f"  {tool.name}: {tool.description}")
```

### Dynamic skill loading

```python
import importlib
from talon_tools import Tool

def load_skills(skill_names: list[str]) -> list[Tool]:
    tools = []
    for name in skill_names:
        module = importlib.import_module(f"talon_tools.{name}.tools")
        tools.extend(module.build_tools())
    return tools

tools = load_skills(["atlassian", "notion", "search"])
```

### Using as agent instructions (drop-in, no code)

Every tool module includes a `SKILL.md` — a self-contained instruction file that teaches an LLM agent how to use that tool. These work with **any agent harness** that supports markdown instructions: VS Code Copilot, Claude Code, Cursor, Windsurf, OpenAI Agents, or your own custom setup.

The idea is simple: install `talon-tools` to get the Python tool functions, then copy the skill instructions into wherever your agent reads them.

**Recommended setup:**

```bash
# 1. Install the tools (gives your agent the actual callable functions)
pip install 'talon-tools[all]'

# 2. Copy the skill bundle into your agent's instruction directory
cp -r skills/ /path/to/your/agent/skills/
```

The [`skills/`](skills/) folder at the repo root contains **only SKILL.md files** — no Python code. It's a ready-to-use bundle you can drop into any agent harness. Each file teaches the LLM what tools are available and how to call them.

| Agent Harness | Where to copy `skills/` contents |
|---------------|----------------------------------|
| VS Code Copilot | `.github/instructions/` (rename to `.instructions.md`) |
| Claude Code | Reference paths in `CLAUDE.md` |
| Cursor | `.cursor/rules/` |
| Windsurf | `.windsurfrules` directory |
| Talon | `agents/skills/` |
| Custom | Inject into system prompt or context |

#### VS Code Copilot

Copy into `.github/instructions/` or `.github/copilot-instructions.md`:

```bash
# As a standalone instruction file
cp talon_tools/earthquake/SKILL.md .github/instructions/earthquake.instructions.md
cp talon_tools/spotify/SKILL.md    .github/instructions/spotify.instructions.md
```

Or reference in your `copilot-instructions.md`:

```markdown
## Available Skills

The following SKILL.md files describe tools you can use:
- [Earthquake](talon_tools/earthquake/SKILL.md) — Real-time USGS earthquake data
- [Spotify](talon_tools/spotify/SKILL.md) — Music playback and search
```

#### Claude Code

Add to your `CLAUDE.md` or `.claude/instructions.md`:

```markdown
## Tools

Read and follow the instructions in these files when asked about the relevant topic:
- talon_tools/earthquake/SKILL.md — Earthquake monitoring
- talon_tools/google/SKILL.md — Gmail, Calendar, Docs, etc.
- talon_tools/wa/SKILL.md — WhatsApp messaging
```

#### Cursor / Windsurf

Add to `.cursor/rules/` or `.windsurfrules`:

```bash
cp talon_tools/earthquake/SKILL.md .cursor/rules/earthquake.md
cp talon_tools/spotify/SKILL.md    .cursor/rules/spotify.md
```

#### Custom agent / system prompt

Concatenate skill files into your system prompt or tool registry:

```python
from pathlib import Path

skills = ["earthquake", "google", "spotify"]
for name in skills:
    content = Path(f"talon_tools/{name}/SKILL.md").read_text()
    # Append to system prompt, inject into context, etc.
```

#### General pattern

The `SKILL.md` files are plain markdown with optional YAML frontmatter. They work anywhere an LLM can read instructions:

```markdown
---
description: One-line summary of what this skill does
dependencies:
  - pip-package-name
---

# Skill Name

When to use, available tools/commands, workflows, and notes.
```

- `description` — Short summary for registries or skill listings
- `dependencies` — Python packages needed (install via `pip install` or `uv pip install`)
- **Body** — The actual instructions the agent reads and follows

### Custom tool

```python
from talon_tools import Tool, ToolResult

async def greet(args: dict) -> ToolResult:
    name = args.get("name", "world")
    return ToolResult(content=f"Hello, {name}!")

def build_tools() -> list[Tool]:
    return [
        Tool(
            name="greet",
            description="Greet someone by name.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name to greet."},
                },
            },
            handler=greet,
        )
    ]
```

## Development

```bash
git clone https://github.com/bingkil/talon-tools.git
cd talon-tools
pip install -e ".[all]"
```

### Project structure

```
talon_tools/
├── credentials.py         # Credential management
├── cli.py                 # Interactive setup CLI
├── types.py               # Tool/ToolResult base types
├── provider.py            # LLM provider interface
├── onboarding/            # Shared onboarding utilities
│   ├── base.py            # OnboardingStep/ToolOnboarding types
│   ├── registry.py        # Auto-discovery of tool onboardings
│   ├── installer.py       # Binary dependency installer
│   └── cookies.py         # Browser cookie extraction
├── google/                # Google Workspace tools
├── microsoft/             # Microsoft 365 tools
├── atlassian/             # Jira & Confluence tools
├── notion/                # Notion tools
├── spotify/               # Spotify tools
├── x/                     # X (Twitter) tools
├── facebook/              # Facebook tools
├── search/                # Web search tools
├── docreader/             # Document parsing tools
├── mcp/                   # MCP client
├── terminal/              # Shell execution tools
├── workspace/             # File system tools
└── ...each module has:
    ├── tools.py           # build_tools() -> list[Tool]
    └── SKILL.md           # Drop-in skill instructions
```

### Adding a new tool module

1. Create `talon_tools/myservice/tools.py` with `build_tools() -> list[Tool]`
2. Create `talon_tools/myservice/onboarding.py` with `get_onboarding() -> ToolOnboarding`
3. Add the import to `talon_tools/onboarding/registry.py`
4. Add optional deps to `pyproject.toml` under `[project.optional-dependencies]`

## Contributing

Contributions welcome! Please:

1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Run the setup CLI to test: `python -m talon_tools.cli setup`
5. Open a PR

## License

[MIT](LICENSE)
