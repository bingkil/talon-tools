"""Spotify tool definitions for LLM agents."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from talon_tools import Tool, ToolResult
from .client import SpotifyClient, format_now_playing, format_track

log = logging.getLogger(__name__)


def build_tools(agent_dir: Path | None = None) -> list[Tool]:
    """Return Spotify tools."""

    client = SpotifyClient(agent_dir=agent_dir)

    # ------------------------------------------------------------------
    # now_playing
    # ------------------------------------------------------------------
    async def handle_now_playing(args: dict[str, Any]) -> ToolResult:
        try:
            state = await client.now_playing()
            return ToolResult(content=format_now_playing(state))
        except RuntimeError as e:
            return ToolResult(content=str(e), is_error=True)
        except Exception as e:
            return ToolResult(content=f"Error fetching playback state: {e}", is_error=True)

    # ------------------------------------------------------------------
    # search
    # ------------------------------------------------------------------
    async def handle_search(args: dict[str, Any]) -> ToolResult:
        try:
            query = args.get("query", "").strip()
            if not query:
                return ToolResult(content="query is required", is_error=True)

            search_type = args.get("type", "track")
            limit = min(int(args.get("limit", 10)), 50)

            result = await client.search(query, search_type, limit)

            lines: list[str] = []

            if search_type == "track":
                items = result.get("tracks", {}).get("items", [])
                lines.append(f"Tracks matching '{query}':")
                for i, item in enumerate(items, 1):
                    lines.append(f"{i}. {format_track(item)}")

            elif search_type == "artist":
                items = result.get("artists", {}).get("items", [])
                lines.append(f"Artists matching '{query}':")
                for i, item in enumerate(items, 1):
                    genres = ", ".join(item.get("genres", [])[:3])
                    pop = item.get("popularity", "?")
                    uri = item.get("uri", "")
                    lines.append(f"{i}. {item['name']} (pop: {pop}{', ' + genres if genres else ''}) | {uri}")

            elif search_type == "album":
                items = result.get("albums", {}).get("items", [])
                lines.append(f"Albums matching '{query}':")
                for i, item in enumerate(items, 1):
                    artists = ", ".join(a["name"] for a in item.get("artists", []))
                    uri = item.get("uri", "")
                    year = item.get("release_date", "")[:4]
                    lines.append(f"{i}. {item['name']} — {artists} ({year}) | {uri}")

            elif search_type == "playlist":
                items = result.get("playlists", {}).get("items", [])
                lines.append(f"Playlists matching '{query}':")
                for i, item in enumerate(items, 1):
                    owner = item.get("owner", {}).get("display_name", "")
                    tracks = item.get("tracks", {}).get("total", "?")
                    uri = item.get("uri", "")
                    lines.append(f"{i}. {item['name']} by {owner} ({tracks} tracks) | {uri}")

            if not lines or len(lines) == 1:
                return ToolResult(content=f"No {search_type}s found for '{query}'.")

            return ToolResult(content="\n".join(lines))

        except RuntimeError as e:
            return ToolResult(content=str(e), is_error=True)
        except Exception as e:
            return ToolResult(content=f"Error searching Spotify: {e}", is_error=True)

    # ------------------------------------------------------------------
    # play
    # ------------------------------------------------------------------
    async def handle_play(args: dict[str, Any]) -> ToolResult:
        try:
            uri = args.get("uri", "").strip()
            uris = [uri] if uri else None
            context_uri = args.get("context_uri", "").strip() or None
            device_id = args.get("device_id", "").strip() or None

            if not uris and not context_uri:
                # Resume current playback
                await client.play(device_id=device_id)
                return ToolResult(content="Playback resumed.")

            await client.play(uris=uris, context_uri=context_uri, device_id=device_id)
            return ToolResult(content=f"Playing {uri or context_uri}")

        except RuntimeError as e:
            return ToolResult(content=str(e), is_error=True)
        except Exception as e:
            return ToolResult(content=f"Error starting playback: {e}", is_error=True)

    # ------------------------------------------------------------------
    # pause
    # ------------------------------------------------------------------
    async def handle_pause(args: dict[str, Any]) -> ToolResult:
        try:
            device_id = args.get("device_id", "").strip() or None
            await client.pause(device_id=device_id)
            return ToolResult(content="Playback paused.")
        except RuntimeError as e:
            return ToolResult(content=str(e), is_error=True)
        except Exception as e:
            return ToolResult(content=f"Error pausing playback: {e}", is_error=True)

    # ------------------------------------------------------------------
    # next / previous
    # ------------------------------------------------------------------
    async def handle_next(args: dict[str, Any]) -> ToolResult:
        try:
            device_id = args.get("device_id", "").strip() or None
            await client.next_track(device_id=device_id)
            return ToolResult(content="Skipped to next track.")
        except RuntimeError as e:
            return ToolResult(content=str(e), is_error=True)
        except Exception as e:
            return ToolResult(content=f"Error skipping track: {e}", is_error=True)

    async def handle_previous(args: dict[str, Any]) -> ToolResult:
        try:
            device_id = args.get("device_id", "").strip() or None
            await client.previous_track(device_id=device_id)
            return ToolResult(content="Went back to previous track.")
        except RuntimeError as e:
            return ToolResult(content=str(e), is_error=True)
        except Exception as e:
            return ToolResult(content=f"Error going back: {e}", is_error=True)

    # ------------------------------------------------------------------
    # volume
    # ------------------------------------------------------------------
    async def handle_volume(args: dict[str, Any]) -> ToolResult:
        try:
            vol = args.get("volume_percent")
            if vol is None:
                return ToolResult(content="volume_percent is required", is_error=True)
            vol = max(0, min(100, int(vol)))
            device_id = args.get("device_id", "").strip() or None
            await client.set_volume(vol, device_id=device_id)
            return ToolResult(content=f"Volume set to {vol}%.")
        except RuntimeError as e:
            return ToolResult(content=str(e), is_error=True)
        except Exception as e:
            return ToolResult(content=f"Error setting volume: {e}", is_error=True)

    # ------------------------------------------------------------------
    # queue
    # ------------------------------------------------------------------
    async def handle_queue(args: dict[str, Any]) -> ToolResult:
        try:
            uri = args.get("uri", "").strip()
            if not uri:
                return ToolResult(content="uri is required", is_error=True)
            device_id = args.get("device_id", "").strip() or None
            await client.add_to_queue(uri, device_id=device_id)
            return ToolResult(content=f"Added to queue: {uri}")
        except RuntimeError as e:
            return ToolResult(content=str(e), is_error=True)
        except Exception as e:
            return ToolResult(content=f"Error adding to queue: {e}", is_error=True)

    # ------------------------------------------------------------------
    # devices
    # ------------------------------------------------------------------
    async def handle_devices(args: dict[str, Any]) -> ToolResult:
        try:
            devices = await client.devices()
            if not devices:
                return ToolResult(content="No active Spotify devices found.")
            lines = ["Available Spotify devices:"]
            for d in devices:
                active = " (active)" if d.get("is_active") else ""
                vol = d.get("volume_percent", "?")
                lines.append(f"  {d['name']} [{d['type']}]{active} — {vol}% | id: {d['id']}")
            return ToolResult(content="\n".join(lines))
        except RuntimeError as e:
            return ToolResult(content=str(e), is_error=True)
        except Exception as e:
            return ToolResult(content=f"Error listing devices: {e}", is_error=True)

    # ------------------------------------------------------------------
    # recently played
    # ------------------------------------------------------------------
    async def handle_recent(args: dict[str, Any]) -> ToolResult:
        try:
            limit = min(int(args.get("limit", 10)), 50)
            items = await client.recently_played(limit=limit)
            if not items:
                return ToolResult(content="No recently played tracks.")
            lines = [f"Recently played ({len(items)} tracks):"]
            for i, item in enumerate(items, 1):
                track = item.get("track", {})
                played_at = item.get("played_at", "")[:16].replace("T", " ")
                lines.append(f"{i}. {format_track(track)}  [{played_at}]")
            return ToolResult(content="\n".join(lines))
        except RuntimeError as e:
            return ToolResult(content=str(e), is_error=True)
        except Exception as e:
            return ToolResult(content=f"Error fetching history: {e}", is_error=True)

    # ------------------------------------------------------------------
    # playlists
    # ------------------------------------------------------------------
    async def handle_create_playlist(args: dict[str, Any]) -> ToolResult:
        try:
            name = args.get("name", "").strip()
            if not name:
                return ToolResult(content="name is required", is_error=True)
            description = args.get("description", "")
            public = args.get("public", False)
            result = await client.create_playlist(name, description, public)
            pl_id = result.get("id", "?")
            uri = result.get("uri", "")
            return ToolResult(content=f"Created playlist: {name} (id: {pl_id}) | {uri}")
        except RuntimeError as e:
            return ToolResult(content=str(e), is_error=True)
        except Exception as e:
            return ToolResult(content=f"Error creating playlist: {e}", is_error=True)

    async def handle_add_to_playlist(args: dict[str, Any]) -> ToolResult:
        try:
            playlist_id = args.get("playlist_id", "").strip()
            uris = args.get("uris", [])
            if not playlist_id:
                return ToolResult(content="playlist_id is required", is_error=True)
            if not uris:
                return ToolResult(content="uris is required (list of Spotify track URIs)", is_error=True)
            await client.add_to_playlist(playlist_id, uris)
            return ToolResult(content=f"Added {len(uris)} track(s) to playlist {playlist_id}")
        except RuntimeError as e:
            return ToolResult(content=str(e), is_error=True)
        except Exception as e:
            return ToolResult(content=f"Error adding to playlist: {e}", is_error=True)

    async def handle_list_playlists(args: dict[str, Any]) -> ToolResult:
        try:
            limit = min(int(args.get("limit", 20)), 50)
            items = await client.list_playlists(limit=limit)
            if not items:
                return ToolResult(content="No playlists found.")
            lines = ["Your Spotify playlists:"]
            for i, pl in enumerate(items, 1):
                tracks = pl.get("tracks", {}).get("total", "?")
                uri = pl.get("uri", "")
                lines.append(f"{i}. {pl['name']} ({tracks} tracks) | {uri} | id: {pl['id']}")
            return ToolResult(content="\n".join(lines))
        except RuntimeError as e:
            return ToolResult(content=str(e), is_error=True)
        except Exception as e:
            return ToolResult(content=f"Error listing playlists: {e}", is_error=True)

    # ------------------------------------------------------------------
    # Tool definitions
    # ------------------------------------------------------------------
    return [
        Tool(
            name="spotify_now_playing",
            description=(
                "Get what's currently playing on Spotify. "
                "Shows track name, artist, album, progress, and device."
            ),
            parameters={"type": "object", "properties": {}},
            handler=handle_now_playing,
        ),
        Tool(
            name="spotify_search",
            description=(
                "Search Spotify for tracks, artists, albums, or playlists. "
                "Returns results with Spotify URIs you can use to play them."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (e.g. 'Bohemian Rhapsody')"},
                    "type": {
                        "type": "string",
                        "enum": ["track", "artist", "album", "playlist"],
                        "description": "What to search for. Default: 'track'",
                    },
                    "limit": {"type": "integer", "description": "Max results (1-50). Default: 10"},
                },
                "required": ["query"],
            },
            handler=handle_search,
        ),
        Tool(
            name="spotify_play",
            description=(
                "Start or resume Spotify playback. "
                "Pass a track URI to play a specific song, a context_uri for an album/playlist, "
                "or nothing to resume current playback. "
                "Use spotify_search first to find URIs."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "uri": {"type": "string", "description": "Spotify track URI (e.g. 'spotify:track:...')"},
                    "context_uri": {"type": "string", "description": "Spotify album/playlist URI to play in context"},
                    "device_id": {"type": "string", "description": "Target device ID (optional, uses active device)"},
                },
                "required": [],
            },
            handler=handle_play,
        ),
        Tool(
            name="spotify_pause",
            description="Pause Spotify playback.",
            parameters={
                "type": "object",
                "properties": {
                    "device_id": {"type": "string", "description": "Device ID (optional)"},
                },
            },
            handler=handle_pause,
        ),
        Tool(
            name="spotify_next",
            description="Skip to the next track on Spotify.",
            parameters={
                "type": "object",
                "properties": {
                    "device_id": {"type": "string", "description": "Device ID (optional)"},
                },
            },
            handler=handle_next,
        ),
        Tool(
            name="spotify_previous",
            description="Go back to the previous track on Spotify.",
            parameters={
                "type": "object",
                "properties": {
                    "device_id": {"type": "string", "description": "Device ID (optional)"},
                },
            },
            handler=handle_previous,
        ),
        Tool(
            name="spotify_volume",
            description="Set the Spotify playback volume (0-100).",
            parameters={
                "type": "object",
                "properties": {
                    "volume_percent": {"type": "integer", "description": "Volume level 0-100"},
                    "device_id": {"type": "string", "description": "Device ID (optional)"},
                },
                "required": ["volume_percent"],
            },
            handler=handle_volume,
        ),
        Tool(
            name="spotify_queue",
            description="Add a track to the Spotify playback queue.",
            parameters={
                "type": "object",
                "properties": {
                    "uri": {"type": "string", "description": "Spotify track URI to queue"},
                    "device_id": {"type": "string", "description": "Device ID (optional)"},
                },
                "required": ["uri"],
            },
            handler=handle_queue,
        ),
        Tool(
            name="spotify_devices",
            description=(
                "List available Spotify devices (phone, desktop, web player, etc). "
                "Returns device names and IDs. Use to find a device_id for playback control."
            ),
            parameters={"type": "object", "properties": {}},
            handler=handle_devices,
        ),
        Tool(
            name="spotify_recently_played",
            description="Get recently played tracks on Spotify.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of tracks to return (1-50). Default: 10"},
                },
            },
            handler=handle_recent,
        ),
        Tool(
            name="spotify_create_playlist",
            description="Create a new Spotify playlist.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Playlist name"},
                    "description": {"type": "string", "description": "Playlist description (optional)"},
                    "public": {"type": "boolean", "description": "Make the playlist public (default: false)"},
                },
                "required": ["name"],
            },
            handler=handle_create_playlist,
        ),
        Tool(
            name="spotify_add_to_playlist",
            description="Add tracks to a Spotify playlist. Use spotify_search first to find track URIs.",
            parameters={
                "type": "object",
                "properties": {
                    "playlist_id": {"type": "string", "description": "Spotify playlist ID"},
                    "uris": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of Spotify track URIs (e.g. ['spotify:track:...'])",
                    },
                },
                "required": ["playlist_id", "uris"],
            },
            handler=handle_add_to_playlist,
        ),
        Tool(
            name="spotify_playlists",
            description="List your Spotify playlists. Returns playlist names, track counts, URIs, and IDs.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max playlists to return (1-50). Default: 20"},
                },
            },
            handler=handle_list_playlists,
        ),
    ]
