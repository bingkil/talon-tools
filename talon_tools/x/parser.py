"""Parse X's deeply nested GraphQL responses into clean data."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Tweet:
    id: str
    text: str
    author: str
    author_handle: str
    created_at: str
    likes: int
    retweets: int
    replies: int
    views: int | None
    url: str


def _extract_tweet(entry: dict) -> Tweet | None:
    """Extract a Tweet from a timeline entry, or None if not a tweet."""
    try:
        content = entry.get("content", {})
        item = content.get("itemContent") or content.get("entryType", "")

        # Timeline entries wrap in itemContent
        if not item:
            return None
        if isinstance(item, str):
            return None

        result = item.get("tweet_results", {}).get("result", {})
        if not result:
            return None

        # Handle tweet-with-visibility wrapper
        if result.get("__typename") == "TweetWithVisibilityResults":
            result = result.get("tweet", result)

        legacy = result.get("legacy", {})
        if not legacy:
            return None

        core = result.get("core", {})
        user_results = core.get("user_results", {}).get("result", {})
        user_legacy = user_results.get("legacy", {})
        # User name/handle can be in legacy or in a nested core object
        user_core = user_results.get("core", {})
        author_name = user_legacy.get("name") or user_core.get("name", "")
        author_handle = user_legacy.get("screen_name") or user_core.get("screen_name", "")

        tweet_id = legacy.get("id_str", result.get("rest_id", ""))
        views_raw = result.get("views", {}).get("count")

        return Tweet(
            id=tweet_id,
            text=legacy.get("full_text", ""),
            author=author_name,
            author_handle=author_handle,
            created_at=legacy.get("created_at", ""),
            likes=legacy.get("favorite_count", 0),
            retweets=legacy.get("retweet_count", 0),
            replies=legacy.get("reply_count", 0),
            views=int(views_raw) if views_raw else None,
            url=f"https://x.com/{user_legacy.get('screen_name', '_')}/status/{tweet_id}",
        )
    except (KeyError, TypeError, ValueError):
        return None


def parse_timeline(raw: dict) -> list[Tweet]:
    """Parse a HomeTimeline or SearchTimeline response into Tweet objects."""
    tweets: list[Tweet] = []

    # Navigate to instructions list
    instructions = _find_instructions(raw)
    if not instructions:
        return tweets

    for instruction in instructions:
        entries = instruction.get("entries", [])
        for entry in entries:
            content = entry.get("content", {})

            # Regular tweet entry
            if content.get("entryType") == "TimelineTimelineItem":
                t = _extract_tweet(entry)
                if t:
                    tweets.append(t)

            # Conversation module (threads)
            elif content.get("entryType") == "TimelineTimelineModule":
                for item in content.get("items", []):
                    sub_entry = {"content": item.get("item", {})}
                    t = _extract_tweet(sub_entry)
                    if t:
                        tweets.append(t)

    return tweets


def parse_tweet_detail(raw: dict) -> Tweet | None:
    """Parse a TweetDetail response into a single Tweet."""
    instructions = _find_instructions(raw)
    if not instructions:
        return None

    for instruction in instructions:
        entries = instruction.get("entries", [])
        for entry in entries:
            content = entry.get("content", {})
            if content.get("entryType") == "TimelineTimelineItem":
                t = _extract_tweet(entry)
                if t:
                    return t
    return None


def _find_instructions(raw: dict) -> list[dict]:
    """Navigate to the instructions array from various response shapes."""
    data = raw.get("data", {})

    # HomeTimeline
    home = data.get("home", {})
    timeline = home.get("home_timeline_urt", {})
    if timeline:
        return timeline.get("instructions", [])

    # SearchTimeline
    search = data.get("search_by_raw_query", {})
    search_tl = search.get("search_timeline", {})
    if search_tl:
        tl = search_tl.get("timeline", {})
        return tl.get("instructions", [])

    # TweetDetail
    threaded = data.get("threaded_conversation_with_injections_v2", {})
    if threaded:
        return threaded.get("instructions", [])

    return []


def format_tweets(tweets: list[Tweet]) -> str:
    """Format tweets into a readable string for the agent."""
    if not tweets:
        return "No tweets found."

    lines: list[str] = []
    for t in tweets:
        views = f" | {t.views:,} views" if t.views else ""
        lines.append(
            f"**{t.author}** (@{t.author_handle})\n"
            f"{t.text}\n"
            f"❤️ {t.likes:,} | 🔁 {t.retweets:,} | 💬 {t.replies:,}{views}\n"
            f"{t.url}"
        )

    return "\n\n---\n\n".join(lines)
