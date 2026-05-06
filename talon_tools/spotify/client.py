"""Spotify API client — async wrappers using httpx directly."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from .auth import get_access_token, API_BASE

log = logging.getLogger(__name__)


class SpotifyClient:
    """Async Spotify API client using httpx."""

    def __init__(self, agent_dir: Path | None = None) -> None:
        self._agent_dir = agent_dir
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        token = get_access_token(self._agent_dir)
        return {"Authorization": f"Bearer {token}"}

    async def _get(self, path: str, params: dict | None = None) -> dict | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{API_BASE}{path}", headers=self._headers(), params=params)
            if resp.status_code == 204:
                return None
            resp.raise_for_status()
            return resp.json()

    async def _put(self, path: str, json: dict | None = None, params: dict | None = None) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.put(f"{API_BASE}{path}", headers=self._headers(), json=json, params=params)
            if resp.status_code not in (200, 204):
                resp.raise_for_status()

    async def _post(self, path: str, json: dict | None = None, params: dict | None = None) -> dict | None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{API_BASE}{path}", headers=self._headers(), json=json, params=params)
            if resp.status_code == 204:
                return None
            resp.raise_for_status()
            return resp.json() if resp.content else None

    # ------------------------------------------------------------------
    # Playback state
    # ------------------------------------------------------------------

    async def now_playing(self) -> dict | None:
        """Return currently playing track info, or None if nothing is playing."""
        return await self._get("/me/player")

    async def recently_played(self, limit: int = 10) -> list[dict]:
        result = await self._get("/me/player/recently-played", params={"limit": limit})
        return (result or {}).get("items", [])

    # ------------------------------------------------------------------
    # Playback control
    # ------------------------------------------------------------------

    async def play(self, uris: list[str] | None = None, context_uri: str | None = None, device_id: str | None = None) -> None:
        params = {"device_id": device_id} if device_id else None
        body: dict[str, Any] = {}
        if uris:
            body["uris"] = uris
        if context_uri:
            body["context_uri"] = context_uri
        await self._put("/me/player/play", json=body or None, params=params)

    async def pause(self, device_id: str | None = None) -> None:
        params = {"device_id": device_id} if device_id else None
        await self._put("/me/player/pause", params=params)

    async def next_track(self, device_id: str | None = None) -> None:
        params = {"device_id": device_id} if device_id else None
        await self._post("/me/player/next", params=params)

    async def previous_track(self, device_id: str | None = None) -> None:
        params = {"device_id": device_id} if device_id else None
        await self._post("/me/player/previous", params=params)

    async def set_volume(self, volume_percent: int, device_id: str | None = None) -> None:
        params: dict[str, Any] = {"volume_percent": volume_percent}
        if device_id:
            params["device_id"] = device_id
        await self._put("/me/player/volume", params=params)

    async def add_to_queue(self, uri: str, device_id: str | None = None) -> None:
        params: dict[str, Any] = {"uri": uri}
        if device_id:
            params["device_id"] = device_id
        await self._post("/me/player/queue", params=params)

    # ------------------------------------------------------------------
    # Search & discovery
    # ------------------------------------------------------------------

    async def search(self, query: str, search_type: str = "track", limit: int = 10) -> dict:
        result = await self._get("/search", params={"q": query, "type": search_type, "limit": limit})
        return result or {}

    async def devices(self) -> list[dict]:
        result = await self._get("/me/player/devices")
        return (result or {}).get("devices", [])

    # ------------------------------------------------------------------
    # Playlists
    # ------------------------------------------------------------------

    async def get_user_id(self) -> str:
        result = await self._get("/me")
        return (result or {}).get("id", "")

    async def create_playlist(self, name: str, description: str = "", public: bool = False) -> dict:
        user_id = await self.get_user_id()
        body = {"name": name, "description": description, "public": public}
        result = await self._post(f"/users/{user_id}/playlists", json=body)
        return result or {}

    async def add_to_playlist(self, playlist_id: str, uris: list[str]) -> None:
        await self._post(f"/playlists/{playlist_id}/tracks", json={"uris": uris})

    async def list_playlists(self, limit: int = 20) -> list[dict]:
        result = await self._get("/me/playlists", params={"limit": limit})
        return (result or {}).get("items", [])


# ------------------------------------------------------------------
# Formatting helpers
# ------------------------------------------------------------------

def format_track(item: dict) -> str:
    """Format a track dict into a readable one-liner."""
    name = item.get("name", "Unknown")
    artists = ", ".join(a["name"] for a in item.get("artists", []))
    album = item.get("album", {}).get("name", "")
    uri = item.get("uri", "")
    duration_ms = item.get("duration_ms", 0)
    mins, secs = divmod(duration_ms // 1000, 60)
    return f"{name} — {artists} [{album}] ({mins}:{secs:02d}) | {uri}"


def format_now_playing(state: dict) -> str:
    """Format the current playback state."""
    if not state:
        return "Nothing is currently playing."

    item = state.get("item")
    if not item:
        return "Playback is active but track info is unavailable."

    is_playing = state.get("is_playing", False)
    progress_ms = state.get("progress_ms", 0)
    duration_ms = item.get("duration_ms", 0)

    def ms_to_mmss(ms: int) -> str:
        m, s = divmod(ms // 1000, 60)
        return f"{m}:{s:02d}"

    name = item.get("name", "Unknown")
    artists = ", ".join(a["name"] for a in item.get("artists", []))
    album = item.get("album", {}).get("name", "")
    uri = item.get("uri", "")
    status = "▶ Playing" if is_playing else "⏸ Paused"
    progress = f"{ms_to_mmss(progress_ms)} / {ms_to_mmss(duration_ms)}"

    device = state.get("device", {})
    device_name = device.get("name", "")
    volume = device.get("volume_percent")

    lines = [
        f"{status}: {name}",
        f"Artist: {artists}",
        f"Album: {album}",
        f"Progress: {progress}",
        f"URI: {uri}",
    ]
    if device_name:
        vol_str = f" — {volume}% volume" if volume is not None else ""
        lines.append(f"Device: {device_name}{vol_str}")

    return "\n".join(lines)
