---
description: Read your X (Twitter) timeline, search tweets, and get tweet details
dependencies:
  - talon-tools[x]
---

# X (Twitter)

Read your X timeline, search tweets, and get individual tweet details using X's internal API. No official API key required.

## When to Use

- "What's on my Twitter?"
- "Show my X timeline"
- "Search X for..."
- "What's trending about...?"
- "Show me that tweet"
- Social media digest / news catch-up

## Installation & Invocation

```bash
pip install 'talon-tools[x]'
```

Set environment variables:

```bash
export X_AUTH_TOKEN=your_auth_token_cookie
export X_CT0=your_ct0_cookie
```

To extract cookies: Chrome DevTools → Application → Cookies → x.com

Load and call:

```python
import asyncio
from talon_tools.x.tools import build_tools

tools = {t.name: t for t in build_tools()}

# Get timeline
result = asyncio.run(tools["x_get_timeline"].handler({"count": 20}))
print(result.content)

# Search
result = asyncio.run(tools["x_search"].handler({"query": "from:elonmusk", "count": 10}))
print(result.content)
```

### Without Python (curl)

```bash
# Get timeline (requires cookies + bearer token)
curl -s "https://x.com/i/api/graphql/HJFjzBgCs16TqxewQOeLNg/HomeTimeline" \
  -H "Authorization: Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA" \
  -H "Cookie: auth_token=$X_AUTH_TOKEN; ct0=$X_CT0" \
  -H "X-Csrf-Token: $X_CT0" \
  -H "Content-Type: application/json" | jq
```

Note: X's internal API is complex (GraphQL with query IDs that change). The Python package handles this automatically. For simple use cases, consider using the `web_search` tool to search X content instead.

## Credentials

- `X_AUTH_TOKEN` — `auth_token` cookie from x.com
- `X_CT0` — `ct0` CSRF token from x.com

## Available Tools

| Tool | Purpose |
|------|---------|
| `x_get_timeline` | Fetch home timeline (default 20, max 50 tweets) |
| `x_search` | Search tweets with optional operators |
| `x_get_tweet` | Get a single tweet by ID |

## Search Operators

- `from:username` — Tweets from a specific user
- `to:username` — Replies to a user
- `has:media` — Tweets with media
- `since:2026-05-01` — Tweets after a date
- `until:2026-05-06` — Tweets before a date
- `min_retweets:100` — Engagement filters

## Notes

- No official API key needed — uses internal GraphQL API with session cookies
- Cookies expire periodically — re-extract from browser when timeline stops loading
- Returns engagement metrics: likes, retweets, replies
- Max 50 results per request
