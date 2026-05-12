"""Spotify OAuth2 token management.

Tokens are encrypted at rest via AES-256 (Fernet). See credential_store.py.

On first use, run the setup script to authorize:
    python -m talon_tools.spotify.setup

This opens a browser for the one-time Spotify approval flow and saves a
token cache file. All subsequent requests auto-refresh silently.

Environment variables required:
    SPOTIFY_CLIENT_ID      — from Spotify Developer Dashboard
    SPOTIFY_CLIENT_SECRET  — from Spotify Developer Dashboard
    SPOTIFY_REDIRECT_URI   — must match what's registered in the app (default: http://localhost:8888/callback)

Optional:
    SPOTIFY_TOKEN_FILE     — path to token cache file (default: ~/.config/talon/spotify_token.json)
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
from pathlib import Path

import httpx
from talon_tools.credentials import get as cred
from talon_tools.credential_store import save_encrypted, load_encrypted

# Scopes needed for full playback control + read + playlist management
SCOPES = " ".join([
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "user-library-read",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
])

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"

DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
DEFAULT_TOKEN_FILE = Path.home() / ".config" / "talon" / "spotify_token.json"


def _token_file(agent_dir: Path | None = None) -> str:
    """Return path to token cache file."""
    env = os.environ.get("SPOTIFY_TOKEN_FILE")
    if env:
        return env
    if agent_dir:
        return str(agent_dir / "spotify_token.json")
    return str(DEFAULT_TOKEN_FILE)


def get_authorize_url(client_id: str, redirect_uri: str) -> str:
    """Build the Spotify authorization URL."""
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    """Exchange an authorization code for tokens."""
    resp = httpx.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    })
    resp.raise_for_status()
    token_info = resp.json()
    token_info["expires_at"] = int(time.time()) + token_info.get("expires_in", 3600)
    return token_info


def _refresh_token(token_info: dict, client_id: str, client_secret: str) -> dict:
    """Refresh an expired access token."""
    resp = httpx.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": token_info["refresh_token"],
        "client_id": client_id,
        "client_secret": client_secret,
    })
    resp.raise_for_status()
    new_info = resp.json()
    # Spotify may not return a new refresh_token — keep old one
    if "refresh_token" not in new_info:
        new_info["refresh_token"] = token_info["refresh_token"]
    new_info["expires_at"] = int(time.time()) + new_info.get("expires_in", 3600)
    return new_info


def get_access_token(agent_dir: Path | None = None) -> str:
    """Return a valid access token, refreshing if needed.

    If no cached token exists, raises RuntimeError with instructions.
    Run `python -m talon_tools.spotify.setup` first.
    """
    token_path = Path(_token_file(agent_dir))
    token_path.parent.mkdir(parents=True, exist_ok=True)

    client_id = cred("SPOTIFY_CLIENT_ID", "")
    client_secret = cred("SPOTIFY_CLIENT_SECRET", "")
    redirect_uri = os.environ.get("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT_URI)

    if not client_id or not client_secret:
        raise RuntimeError(
            "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set. "
            "Register an app at https://developer.spotify.com/dashboard"
        )

    cached = load_encrypted(token_path)
    if not cached:
        auth_url = get_authorize_url(client_id, redirect_uri)
        raise RuntimeError(
            f"No Spotify token found. Run the setup script to authorize:\n"
            f"    python -m talon_tools.spotify.setup\n\n"
            f"Or manually visit: {auth_url}"
        )

    token_info = json.loads(cached)

    # Refresh if expired (with 60s buffer)
    if token_info.get("expires_at", 0) < time.time() + 60:
        token_info = _refresh_token(token_info, client_id, client_secret)
        save_encrypted(json.dumps(token_info), token_path)

    return token_info["access_token"]
