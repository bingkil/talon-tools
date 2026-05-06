"""
YouTube integration — search, video info, playlists, and transcripts.

Uses YouTube Data API v3 via google-api-python-client.
"""

from __future__ import annotations

import re
from googleapiclient.discovery import build

from .auth import get_credentials

_services: dict[str, object] = {}


def _service(token_file=None):
    key = str(token_file) if token_file else "__default__"
    if key not in _services:
        _services[key] = build("youtube", "v3", credentials=get_credentials(token_file))
    return _services[key]


def _duration_to_str(iso_duration: str) -> str:
    """Convert ISO 8601 duration (PT1H2M3S) to readable string."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration or "")
    if not m:
        return iso_duration or "?"
    h, mins, s = m.groups()
    parts = []
    if h:
        parts.append(f"{h}h")
    if mins:
        parts.append(f"{mins}m")
    if s:
        parts.append(f"{s}s")
    return " ".join(parts) or "0s"


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_videos(query: str, max_results: int = 5, token_file=None) -> str:
    """Search YouTube for videos."""
    svc = _service(token_file)
    resp = svc.search().list(
        part="snippet",
        q=query,
        type="video",
        maxResults=max_results,
    ).execute()

    items = resp.get("items", [])
    if not items:
        return f"No videos found for: {query}"

    lines = []
    for item in items:
        vid_id = item["id"]["videoId"]
        snippet = item["snippet"]
        title = snippet["title"]
        channel = snippet["channelTitle"]
        lines.append(f"[{vid_id}] {title} — {channel} | https://youtu.be/{vid_id}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Video info
# ---------------------------------------------------------------------------

def get_video_info(video_id: str, token_file=None) -> str:
    """Get detailed info about a video."""
    svc = _service(token_file)
    resp = svc.videos().list(
        part="snippet,contentDetails,statistics",
        id=video_id,
    ).execute()

    items = resp.get("items", [])
    if not items:
        return f"Video not found: {video_id}"

    v = items[0]
    snippet = v["snippet"]
    stats = v.get("statistics", {})
    details = v.get("contentDetails", {})

    lines = [
        f"Title: {snippet['title']}",
        f"Channel: {snippet['channelTitle']}",
        f"Published: {snippet['publishedAt'][:10]}",
        f"Duration: {_duration_to_str(details.get('duration', ''))}",
        f"Views: {stats.get('viewCount', '?')}",
        f"Likes: {stats.get('likeCount', '?')}",
        f"Comments: {stats.get('commentCount', '?')}",
        f"URL: https://youtu.be/{video_id}",
        "---",
        snippet.get("description", "")[:500],
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------

def list_playlists(max_results: int = 10, token_file=None) -> str:
    """List the user's YouTube playlists."""
    svc = _service(token_file)
    resp = svc.playlists().list(
        part="snippet,contentDetails",
        mine=True,
        maxResults=max_results,
    ).execute()

    items = resp.get("items", [])
    if not items:
        return "No playlists found."

    lines = []
    for pl in items:
        count = pl["contentDetails"]["itemCount"]
        lines.append(f"[{pl['id']}] {pl['snippet']['title']} ({count} videos)")

    return "\n".join(lines)


def get_playlist_items(playlist_id: str, max_results: int = 20, token_file=None) -> str:
    """List videos in a playlist."""
    svc = _service(token_file)
    resp = svc.playlistItems().list(
        part="snippet",
        playlistId=playlist_id,
        maxResults=max_results,
    ).execute()

    items = resp.get("items", [])
    if not items:
        return f"No items in playlist: {playlist_id}"

    lines = []
    for i, item in enumerate(items, 1):
        snippet = item["snippet"]
        vid_id = snippet.get("resourceId", {}).get("videoId", "")
        lines.append(f"{i}. {snippet['title']} | https://youtu.be/{vid_id}")

    return "\n".join(lines)


def add_to_playlist(playlist_id: str, video_id: str, token_file=None) -> str:
    """Add a video to a playlist."""
    svc = _service(token_file)
    svc.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id,
                },
            }
        },
    ).execute()
    return f"Added {video_id} to playlist {playlist_id}"


def create_playlist(title: str, description: str = "", privacy: str = "private", token_file=None) -> str:
    """Create a new playlist."""
    svc = _service(token_file)
    resp = svc.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": privacy},
        },
    ).execute()
    return f"Created playlist: {resp['snippet']['title']} (id: {resp['id']})"


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------

def get_transcript(video_id: str, language: str = "en", **_kwargs) -> str:
    """Get video captions/transcript using yt-dlp.

    Extracts subtitles (manual or auto-generated) for the given video.
    """
    import yt_dlp
    import httpx

    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": [language],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    subs = info.get("subtitles", {}).get(language)
    if not subs:
        subs = info.get("automatic_captions", {}).get(language)

    if not subs:
        return f"No captions available for video: {video_id}"

    sub_url = subs[0]["url"]
    ext = subs[0]["ext"]

    resp = httpx.get(sub_url, follow_redirects=True)
    if resp.status_code != 200:
        return f"Could not download captions: HTTP {resp.status_code}"

    if ext == "vtt":
        lines = []
        for line in resp.text.splitlines():
            line = line.strip()
            if not line or line.startswith("WEBVTT") or "-->" in line or line.isdigit():
                continue
            lines.append(line)
        return "\n".join(lines) if lines else "Transcript is empty."
    elif ext in ("srv3", "json3"):
        import json
        data = json.loads(resp.text)
        events = data.get("events", [])
        lines = []
        for event in events:
            segs = event.get("segs")
            if segs:
                text = "".join(s.get("utf8", "") for s in segs).strip()
                if text:
                    lines.append(text)
        return "\n".join(lines) if lines else "Transcript is empty."
    else:
        return resp.text


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

_DEFAULT_OUTPUT_DIR = str(__import__("pathlib").Path.home() / "Downloads")


def download_video(video_id: str, resolution: str = "best", output_dir: str = _DEFAULT_OUTPUT_DIR, **_kwargs) -> str:
    """Download a YouTube video as MP4.

    Args:
        video_id: YouTube video ID or full URL.
        resolution: Desired resolution (e.g. '720p', '1080p', 'best').
        output_dir: Directory to save the file (default: ~/Downloads).
    """
    import os
    import yt_dlp

    url = _to_url(video_id)
    os.makedirs(output_dir, exist_ok=True)

    if resolution == "best":
        fmt = "bestvideo+bestaudio/best"
    else:
        height = resolution.replace("p", "")
        fmt = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"

    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")
    ydl_opts = {
        "format": fmt,
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        # Extension may differ after merge
        base = os.path.splitext(filename)[0]
        mp4_path = base + ".mp4"
        if os.path.exists(mp4_path):
            filename = mp4_path

    return f"Downloaded: {filename}"


def download_audio(video_id: str, output_dir: str = _DEFAULT_OUTPUT_DIR, **_kwargs) -> str:
    """Download a YouTube video as MP3 audio.

    Args:
        video_id: YouTube video ID or full URL.
        output_dir: Directory to save the file (default: ~/Downloads).
    """
    import os
    import yt_dlp

    url = _to_url(video_id)
    os.makedirs(output_dir, exist_ok=True)

    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        mp3_path = os.path.splitext(filename)[0] + ".mp3"

    return f"Downloaded: {mp3_path}"


def get_formats(video_id: str, **_kwargs) -> str:
    """List available download formats/resolutions for a video."""
    import yt_dlp

    url = _to_url(video_id)
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = info.get("formats", [])
    # Show video formats with resolution
    video_fmts = [
        f for f in formats
        if f.get("vcodec", "none") != "none" and f.get("height")
    ]

    # Deduplicate by height
    seen = set()
    lines = []
    for f in sorted(video_fmts, key=lambda x: x.get("height", 0), reverse=True):
        h = f["height"]
        if h in seen:
            continue
        seen.add(h)
        size = f.get("filesize") or f.get("filesize_approx")
        size_str = f" (~{size // 1_048_576}MB)" if size else ""
        lines.append(f"{h}p — {f.get('ext', '?')}{size_str}")

    return "\n".join(lines) if lines else "No formats found."


def _to_url(video_id_or_url: str) -> str:
    """Convert a video ID or URL to a full YouTube URL."""
    if video_id_or_url.startswith(("http://", "https://")):
        return video_id_or_url
    return f"https://www.youtube.com/watch?v={video_id_or_url}"
