---
description: Read your Facebook news feed posts from friends and pages
dependencies:
  - talon-tools[facebook]
---

# Facebook Feed

Fetch your Facebook news feed using headless browser automation. Returns recent posts from friends and pages you follow.

## When to Use

- "What's on my Facebook?"
- "Show me my Facebook feed"
- "Any new posts from friends?"
- Social media digest / catch-up

## Installation & Invocation

```bash
pip install 'talon-tools[facebook]'
playwright install chromium
```

Set environment variables:

```bash
export FB_C_USER=your_c_user_cookie
export FB_XS=your_xs_cookie
# Optional:
export FB_DATR=your_datr_cookie
export FB_FR=your_fr_cookie
```

To extract cookies: Chrome DevTools → Application → Cookies → facebook.com

Load and call:

```python
import asyncio
from talon_tools.facebook.tools import build_tools

tools = {t.name: t for t in build_tools()}
result = asyncio.run(tools["fb_get_feed"].handler({"count": 10}))
print(result.content)
```

### Without Python

Facebook has no public API for feed reading. This tool uses headless browser automation (Playwright) which requires Python. There is no simple curl alternative — Facebook's web interface requires JavaScript execution and session management.

If you need Facebook data without Python, consider using a browser extension or manual access.

## Credentials

- `FB_C_USER` — `c_user` cookie from facebook.com
- `FB_XS` — `xs` cookie from facebook.com
- Optional: `FB_DATR`, `FB_FR` — additional cookies for stability

## Available Tools

| Tool | Purpose |
|------|---------|
| `fb_get_feed` | Fetch recent news feed posts (default 10, max ~20) |

## Notes

- Uses headless browser (Playwright) — first call may take 10–20 seconds
- Returns: author, text, timestamp, and URL for each post
- Requires your own Facebook session cookies (not app-based auth)
- Cookies expire periodically — re-extract when feed stops loading
