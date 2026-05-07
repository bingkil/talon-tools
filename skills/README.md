# Skill Bundle

Drop-in skill instructions for AI agents. Each folder contains a single `SKILL.md` file that teaches an LLM how to use that tool — no Python code required.

## Usage

Copy the entire `skills/` folder (or individual tool folders) into your agent's instruction directory:

```bash
# Copy all skills
cp -r skills/ /path/to/your/agent/skills/

# Or just the ones you need
cp -r skills/earthquake /path/to/your/agent/skills/
cp -r skills/spotify    /path/to/your/agent/skills/
```

### Where to put them

| Agent Harness | Target Directory |
|---------------|-----------------|
| VS Code Copilot | `.github/instructions/` (rename to `.instructions.md`) |
| Claude Code | Reference in `CLAUDE.md` |
| Cursor | `.cursor/rules/` |
| Windsurf | `.windsurfrules` directory |
| Talon | `agents/skills/` |
| Custom | Inject into system prompt or tool registry |

## Available Skills

| Skill | Description |
|-------|-------------|
| `atlassian` | Jira & Confluence — issues, pages, search |
| `catholic` | Daily Catholic mass readings |
| `docreader` | Extract text from PDF, Word, Excel, PowerPoint |
| `earthquake` | Real-time USGS earthquake monitoring |
| `facebook` | Facebook news feed |
| `google` | Gmail, Calendar, Docs, Drive, Sheets, Keep, Tasks, Photos, YouTube |
| `microsoft` | Outlook, Calendar, Teams via Microsoft Graph |
| `notion` | Notion pages & databases |
| `search` | Web search via DuckDuckGo |
| `servicenow` | ServiceNow cases & change requests |
| `spotify` | Spotify playback & music search |
| `terminal` | Shell command execution |
| `wa` | WhatsApp messaging via wacli |
| `workspace` | Sandboxed file system operations |
| `x` | X (Twitter) timeline & search |
