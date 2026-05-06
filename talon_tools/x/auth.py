"""Auth helpers — load cookies and build X request headers."""

from __future__ import annotations

import json
from pathlib import Path
from talon_tools.credentials import get as cred

# Public bearer token embedded in X's web client JS — shared by all users.
BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)


def load_cookies() -> dict[str, str]:
    """Load auth_token and ct0 from env vars or cookies.json fallback.

    Env vars: X_AUTH_TOKEN, X_CT0
    Fallback: cookies.json next to this file or in cwd.
    """
    auth_token = cred("X_AUTH_TOKEN", "")
    ct0 = cred("X_CT0", "")

    if auth_token and ct0:
        return {"auth_token": auth_token, "ct0": ct0}

    # Fallback: cookies.json
    for candidate in [Path("cookies.json"), Path(__file__).parent / "cookies.json"]:
        if candidate.exists():
            data = json.loads(candidate.read_text())
            return {"auth_token": data["auth_token"], "ct0": data["ct0"]}

    raise RuntimeError(
        "X cookies not found. Set X_AUTH_TOKEN and X_CT0 env vars, "
        "or place a cookies.json with auth_token and ct0."
    )


def build_headers(ct0: str) -> dict[str, str]:
    """Build the full request headers for X GraphQL endpoints."""
    return {
        "authorization": f"Bearer {BEARER_TOKEN}",
        "x-csrf-token": ct0,
        "x-twitter-active-user": "yes",
        "x-twitter-client-language": "en",
        "x-twitter-auth-type": "OAuth2Session",
        "content-type": "application/json",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    }
