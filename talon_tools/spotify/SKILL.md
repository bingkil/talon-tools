---
description: Control Spotify playback, search music, and manage devices
dependencies:
  - talon-tools[spotify]
---

# Spotify

Control Spotify playback, search the music catalog, and manage connected devices via the Spotify Web API.

## When to Use

- "Play some music"
- "What's playing right now?"
- "Search for songs by..."
- "Skip this track"
- "Pause the music"
- "Turn the volume up"
- "Play this playlist"
- "What devices are available?"

## Installation & Invocation

```bash
pip install 'talon-tools[spotify]'
```

Run interactive setup to complete OAuth:

```bash
python -m talon_tools.cli setup spotify
```

This opens a browser for Spotify authorization. The token is stored and refreshed automatically.

Load and call:

```python
import asyncio
from talon_tools.spotify.tools import build_tools

tools = {t.name: t for t in build_tools()}

# What's playing?
result = asyncio.run(tools["spotify_now_playing"].handler({}))
print(result.content)

# Search
result = asyncio.run(tools["spotify_search"].handler({"query": "bohemian rhapsody", "type": "track"}))
print(result.content)
```

### Without Python (curl)

If you already have an access token (from the OAuth flow):

```bash
# Now playing
curl -s -H "Authorization: Bearer $SPOTIFY_TOKEN" \
  "https://api.spotify.com/v1/me/player" | jq '{track: .item.name, artist: .item.artists[0].name, album: .item.album.name}'

# Search
curl -s -H "Authorization: Bearer $SPOTIFY_TOKEN" \
  "https://api.spotify.com/v1/search?q=bohemian+rhapsody&type=track&limit=5" | jq '.tracks.items[] | {name, artist: .artists[0].name, uri}'

# Play a track
curl -s -X PUT -H "Authorization: Bearer $SPOTIFY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"uris":["spotify:track:4u7EnebtmKWzUH433cf5Qv"]}' \
  "https://api.spotify.com/v1/me/player/play"

# Pause / Next / Previous
curl -s -X PUT -H "Authorization: Bearer $SPOTIFY_TOKEN" "https://api.spotify.com/v1/me/player/pause"
curl -s -X POST -H "Authorization: Bearer $SPOTIFY_TOKEN" "https://api.spotify.com/v1/me/player/next"
```

Note: Getting the initial OAuth token still requires the Python setup flow (`python -m talon_tools.cli setup spotify`) or manual OAuth at https://developer.spotify.com.

## Credentials

Spotify OAuth token (managed automatically after `setup spotify`). Requires Spotify Premium for playback control.

## Available Tools

| Tool | Purpose |
|------|---------|
| `spotify_now_playing` | Get current playback state (track, artist, progress) |
| `spotify_search` | Search for tracks, artists, albums, or playlists |
| `spotify_play` | Start or resume playback (optional: specific track/album/playlist) |
| `spotify_pause` | Pause playback |
| `spotify_next` | Skip to next track |
| `spotify_previous` | Go back to previous track |
| `spotify_volume` | Set volume (0–100) |
| `spotify_queue` | Add a track to the playback queue |
| `spotify_devices` | List available playback devices |
| `spotify_recently_played` | List recently played tracks |
| `spotify_playlists` | List user's playlists |
| `spotify_create_playlist` | Create a new playlist |
| `spotify_add_to_playlist` | Add tracks to a playlist |

## Workflow: Play a Song

1. `spotify_search` with query and `type=track`
2. `spotify_play` with the track URI from results

## Workflow: Play a Playlist

1. `spotify_search` with query and `type=playlist`
2. `spotify_play` with the `context_uri` from results

## Notes

- Requires an active Spotify device (Premium recommended for playback control)
- Device ID is optional — defaults to the currently active device
- Search types: `track`, `artist`, `album`, `playlist`
- Volume range: 0 (mute) to 100 (max)
