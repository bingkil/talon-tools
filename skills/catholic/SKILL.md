---
description: Get daily Catholic mass readings (first reading, psalm, gospel, etc.)
dependencies:
  - talon-tools[catholic]
---

# Catholic Daily Readings

Fetch the daily Catholic mass readings from Universalis. Returns the first reading, responsorial psalm, second reading, gospel acclamation, and gospel with full text and references.

## When to Use

- "What are today's readings?"
- "Give me the gospel for today"
- "What's the mass reading for December 25?"
- "Read me the psalm of the day"
- Morning devotional / daily reflection

## Installation & Invocation

```bash
pip install 'talon-tools[catholic]'
```

Load and call:

```python
import asyncio
from talon_tools.catholic.tools import build_tools

tools = {t.name: t for t in build_tools()}
result = asyncio.run(tools["daily_mass_readings"].handler({}))
print(result.content)  # Today's readings

# Specific date
result = asyncio.run(tools["daily_mass_readings"].handler({"date": "2026-12-25"}))
```

No credentials required.

### Without Python (curl)

```bash
# Today's readings
curl -s "https://universalis.com/today.htm" | grep -A 50 '<h2>First Reading'

# Specific date (YYYY-MM-DD → YYYYMMDD)
curl -s "https://universalis.com/20261225.htm"
```

The HTML needs parsing — extract content between `<h2>` section headers. For a cleaner approach, use the JSON endpoint if available, or pipe through an HTML-to-text tool like `lynx -dump` or `w3m -dump`.

## Available Tools

| Tool | Purpose |
|------|---------|
| `daily_mass_readings` | Fetch mass readings for today or a specific date |

## Usage

Ask for today's readings or specify a date in `YYYY-MM-DD` format.

The tool returns:
- **First Reading** — Old Testament or Acts passage with reference
- **Responsorial Psalm** — Psalm response with refrain
- **Second Reading** — Epistle passage (when available)
- **Gospel Acclamation** — Alleluia verse
- **Gospel** — Gospel passage with reference

## Notes

- No API key required — uses public liturgical texts from universalis.com
- Date format: `YYYY-MM-DD` (defaults to today if omitted)
- Some days have no second reading (weekday masses)
