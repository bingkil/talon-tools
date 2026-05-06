"""
USGS Earthquake data client.

Two data sources:
  1. Real-time GeoJSON feeds — optimised for "latest N hours/days/weeks" queries.
     Base URL: https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/
     Pattern:  {magnitude}_{period}.geojson
       magnitude: all | 1.0 | 2.5 | 4.5 | significant
       period:    hour | day | week | month

  2. FDSN Event API — full parametric search (time range, bounding box, radius).
     Base URL: https://earthquake.usgs.gov/fdsnws/event/1/query
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import urllib.request
import urllib.parse

FEED_BASE = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary"
FDSN_BASE = "https://earthquake.usgs.gov/fdsnws/event/1/query"

VALID_MAGNITUDES = {"all", "1.0", "2.5", "4.5", "significant"}
VALID_PERIODS = {"hour", "day", "week", "month"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch(url: str) -> dict:
    """Synchronous HTTP GET returning parsed JSON."""
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode())


async def _async_fetch(url: str) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch, url)


def _format_ts(ms: int) -> str:
    """Convert USGS millisecond timestamp to human-readable UTC string."""
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _format_feature(f: dict) -> dict:
    """Flatten a GeoJSON feature into a clean dict."""
    p = f.get("properties", {})
    geo = f.get("geometry", {})
    coords = geo.get("coordinates", [None, None, None])
    return {
        "id": f.get("id"),
        "magnitude": p.get("mag"),
        "place": p.get("place"),
        "time": _format_ts(p["time"]) if p.get("time") else None,
        "depth_km": coords[2],
        "latitude": coords[1],
        "longitude": coords[0],
        "alert": p.get("alert"),
        "tsunami": bool(p.get("tsunami")),
        "url": p.get("url"),
        "felt": p.get("felt"),
        "significance": p.get("sig"),
        "status": p.get("status"),
    }


def _summarise(features: list[dict], limit: int) -> str:
    """Render a list of earthquake features as plain text."""
    if not features:
        return "No earthquakes found matching the criteria."

    items = features[:limit]
    lines = [f"Found {len(features)} earthquake(s). Showing top {len(items)}:\n"]
    for eq in items:
        mag = eq["magnitude"]
        place = eq["place"] or "Unknown location"
        ts = eq["time"] or "Unknown time"
        depth = eq["depth_km"]
        alert = eq["alert"] or "none"
        tsunami = " ⚠ TSUNAMI WARNING" if eq["tsunami"] else ""
        lines.append(
            f"M{mag} — {place}\n"
            f"  Time:  {ts}\n"
            f"  Depth: {depth} km\n"
            f"  Alert: {alert}{tsunami}\n"
            f"  URL:   {eq['url']}\n"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_recent_earthquakes(
    magnitude: str = "2.5",
    period: str = "day",
    limit: int = 10,
) -> str:
    """
    Fetch earthquakes from USGS real-time feed.

    magnitude: all | 1.0 | 2.5 | 4.5 | significant
    period:    hour | day | week | month
    limit:     max events to return (1-100)
    """
    mag = magnitude if magnitude in VALID_MAGNITUDES else "2.5"
    per = period if period in VALID_PERIODS else "day"
    limit = max(1, min(limit, 100))

    url = f"{FEED_BASE}/{mag}_{per}.geojson"
    data = await _async_fetch(url)

    features = [_format_feature(f) for f in data.get("features", [])]
    # Sort by time descending (most recent first)
    features.sort(key=lambda x: x["time"] or "", reverse=True)

    meta = data.get("metadata", {})
    header = (
        f"USGS feed: {meta.get('title', 'Earthquakes')}\n"
        f"Generated: {_format_ts(meta['generated']) if meta.get('generated') else 'N/A'}\n\n"
    )
    return header + _summarise(features, limit)


async def query_earthquakes(
    min_magnitude: float | None = None,
    max_magnitude: float | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    max_radius_km: float | None = None,
    min_latitude: float | None = None,
    max_latitude: float | None = None,
    min_longitude: float | None = None,
    max_longitude: float | None = None,
    limit: int = 10,
    order_by: str = "time",
) -> str:
    """
    Query USGS FDSN event API with custom parameters.

    Time strings use ISO8601: e.g. "2026-05-01" or "2026-05-01T12:00:00".
    order_by: time | time-asc | magnitude | magnitude-asc
    """
    params: dict[str, Any] = {"format": "geojson", "orderby": order_by}

    if min_magnitude is not None:
        params["minmagnitude"] = min_magnitude
    if max_magnitude is not None:
        params["maxmagnitude"] = max_magnitude
    if start_time:
        params["starttime"] = start_time
    if end_time:
        params["endtime"] = end_time

    # Circle search
    if latitude is not None and longitude is not None and max_radius_km is not None:
        params["latitude"] = latitude
        params["longitude"] = longitude
        params["maxradiuskm"] = max_radius_km
    # Rectangle search
    elif any(v is not None for v in [min_latitude, max_latitude, min_longitude, max_longitude]):
        if min_latitude is not None:
            params["minlatitude"] = min_latitude
        if max_latitude is not None:
            params["maxlatitude"] = max_latitude
        if min_longitude is not None:
            params["minlongitude"] = min_longitude
        if max_longitude is not None:
            params["maxlongitude"] = max_longitude

    limit = max(1, min(limit, 100))
    params["limit"] = limit

    qs = urllib.parse.urlencode(params)
    url = f"{FDSN_BASE}?{qs}"

    data = await _async_fetch(url)
    features = [_format_feature(f) for f in data.get("features", [])]

    meta = data.get("metadata", {})
    header = (
        f"USGS FDSN query — {meta.get('count', len(features))} event(s) found\n"
        f"Generated: {_format_ts(meta['generated']) if meta.get('generated') else 'N/A'}\n\n"
    )
    return header + _summarise(features, limit)
