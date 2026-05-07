---
description: Search the web using DuckDuckGo (no API key needed)
dependencies:
  - talon-tools[search]
---

# Web Search

Search the web using DuckDuckGo. Returns titles, URLs, and snippets — no API key required.

## When to Use

- "Search for..."
- "Look up..."
- "What is...?"
- "Find information about..."
- Fact-checking or research
- Finding documentation, tutorials, or news

## Installation & Invocation

```bash
pip install 'talon-tools[search]'
```

No credentials required.

Load and call:

```python
import asyncio
from talon_tools.search.tools import build_tools

tools = {t.name: t for t in build_tools()}
result = asyncio.run(tools["web_search"].handler({"query": "python async best practices"}))
print(result.content)
```

### Without Python (curl)

```bash
# DuckDuckGo Lite (HTML, pipe to text extractor)
curl -s "https://lite.duckduckgo.com/lite/?q=python+async+best+practices" | lynx -stdin -dump | head -80

# DuckDuckGo Instant Answer API (JSON, limited)
curl -s "https://api.duckduckgo.com/?q=python+async&format=json&no_html=1" | jq '{heading: .Heading, abstract: .Abstract, url: .AbstractURL}'
```

## Available Tools

| Tool | Purpose |
|------|---------|
| `web_search` | Search the web via DuckDuckGo |

## Parameters

- `query` — Search query (required)
- `max_results` — Number of results (default 5, max 10)

## Notes

- No API key or account required
- Returns: title, URL, and snippet per result
- Use specific queries for better results
- Good for general knowledge, news, and documentation lookups
