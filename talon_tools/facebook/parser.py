"""Parse Facebook feed data from HTML/JSON text using regex extraction."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime


@dataclass
class FBPost:
    author: str
    author_slug: str
    text: str
    url: str
    created_at: int  # unix timestamp


def parse_feed_html(html: str) -> list[FBPost]:
    """Extract feed posts from combined HTML + GraphQL response text.

    Correlates story metadata (creation_time + url) with nearby message text
    and author names using positional proximity.
    """
    # Collect story entries: creation_time + url
    story_map: dict[str, dict] = {}  # url -> {time, pos}
    for m in re.finditer(r'"story":\{"creation_time":(\d+),"url":"([^"]+)"', html):
        url = m.group(2).replace("\\/", "/")
        if url not in story_map:
            story_map[url] = {"time": int(m.group(1)), "pos": m.start()}

    # Collect message texts with positions
    msg_list: list[dict] = []
    for m in re.finditer(r'"message":\{"text":"([^"]{5,})"', html):
        raw = m.group(1)
        try:
            text = json.loads('"' + raw + '"')
        except (json.JSONDecodeError, UnicodeDecodeError):
            text = raw
        msg_list.append({"text": text, "pos": m.start()})

    # Build posts by correlating stories with nearby messages
    posts: list[FBPost] = []
    seen_urls: set[str] = set()

    for url, story in story_map.items():
        if url in seen_urls:
            continue
        seen_urls.add(url)

        pos = story["pos"]

        # Find closest message after this story (within 50k chars)
        text = ""
        for msg in msg_list:
            if msg["pos"] > pos and msg["pos"] - pos < 50000:
                text = msg["text"]
                break

        # Extract author slug from URL
        slug_match = re.match(r"https://www\.facebook\.com/([^/?]+)", url)
        slug = slug_match.group(1) if slug_match else "unknown"

        # Find author display name near this story
        back_start = max(0, pos - 5000)
        back_ctx = html[back_start:pos]
        name_matches = re.findall(r'"name":"([^"]{2,60})"', back_ctx)
        author = name_matches[-1] if name_matches else slug

        posts.append(FBPost(
            author=author,
            author_slug=slug,
            text=text,
            url=url,
            created_at=story["time"],
        ))

    # Sort by time descending (newest first)
    posts.sort(key=lambda p: p.created_at, reverse=True)
    return posts


def format_posts(posts: list[FBPost]) -> str:
    """Format posts into a readable string for the agent."""
    if not posts:
        return "No posts found in feed."

    lines: list[str] = []
    for p in posts:
        ts = datetime.fromtimestamp(p.created_at).strftime("%Y-%m-%d %H:%M")
        slug = f" (@{p.author_slug})" if p.author_slug else ""
        text_preview = p.text[:500] if p.text else "(image/video only)"
        lines.append(
            f"**{p.author}**{slug} — {ts}\n"
            f"{text_preview}\n"
            f"{p.url}"
        )

    return "\n\n---\n\n".join(lines)
