"""Earthquake tool definitions for LLM agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from talon_tools import Tool, ToolResult
from .client import get_recent_earthquakes, query_earthquakes, _async_fetch, _format_feature, _summarise, FEED_BASE
from .dedup import load_seen, save_seen, filter_new


def build_tools(agent_dir: Path | None = None) -> list[Tool]:
    """Return earthquake tools."""

    # ------------------------------------------------------------------
    # Tool 1: recent feed
    # ------------------------------------------------------------------
    async def handle_recent(args: dict[str, Any]) -> ToolResult:
        try:
            result = await get_recent_earthquakes(
                magnitude=args.get("magnitude", "2.5"),
                period=args.get("period", "day"),
                limit=int(args.get("limit", 10)),
            )
            return ToolResult(content=result)
        except Exception as e:
            return ToolResult(content=f"Error fetching earthquake feed: {e}", is_error=True)

    recent_tool = Tool(
        name="get_recent_earthquakes",
        description=(
            "Get recent earthquakes from the USGS real-time feed. "
            "Returns the latest events filtered by minimum magnitude and time window. "
            "Use this for quick 'what happened recently' queries."
        ),
        parameters={
            "type": "object",
            "properties": {
                "magnitude": {
                    "type": "string",
                    "enum": ["all", "1.0", "2.5", "4.5", "significant"],
                    "description": (
                        "Minimum magnitude filter. "
                        "'all' = everything, '1.0' = M1.0+, '2.5' = M2.5+, "
                        "'4.5' = M4.5+, 'significant' = significant events only. "
                        "Default: '2.5'."
                    ),
                },
                "period": {
                    "type": "string",
                    "enum": ["hour", "day", "week", "month"],
                    "description": "Time window to look back. Default: 'day'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max events to return (1-100). Default: 10.",
                },
            },
            "required": [],
        },
        handler=handle_recent,
    )

    # ------------------------------------------------------------------
    # Tool 2: FDSN parametric query
    # ------------------------------------------------------------------
    async def handle_query(args: dict[str, Any]) -> ToolResult:
        try:
            result = await query_earthquakes(
                min_magnitude=args.get("min_magnitude"),
                max_magnitude=args.get("max_magnitude"),
                start_time=args.get("start_time"),
                end_time=args.get("end_time"),
                latitude=args.get("latitude"),
                longitude=args.get("longitude"),
                max_radius_km=args.get("max_radius_km"),
                min_latitude=args.get("min_latitude"),
                max_latitude=args.get("max_latitude"),
                min_longitude=args.get("min_longitude"),
                max_longitude=args.get("max_longitude"),
                limit=int(args.get("limit", 10)),
                order_by=args.get("order_by", "time"),
            )
            return ToolResult(content=result)
        except Exception as e:
            return ToolResult(content=f"Error querying earthquakes: {e}", is_error=True)

    query_tool = Tool(
        name="query_earthquakes",
        description=(
            "Advanced earthquake search using the USGS FDSN Event API. "
            "Filter by magnitude range, custom time range, geographic bounding box, "
            "or a radius around a lat/lon point. "
            "Use this for precise historical or location-specific queries."
        ),
        parameters={
            "type": "object",
            "properties": {
                "min_magnitude": {
                    "type": "number",
                    "description": "Minimum magnitude (e.g. 4.0).",
                },
                "max_magnitude": {
                    "type": "number",
                    "description": "Maximum magnitude.",
                },
                "start_time": {
                    "type": "string",
                    "description": "Start time in ISO8601 format, e.g. '2026-05-01' or '2026-05-01T00:00:00'.",
                },
                "end_time": {
                    "type": "string",
                    "description": "End time in ISO8601 format.",
                },
                "latitude": {
                    "type": "number",
                    "description": "Latitude for radius search (requires longitude and max_radius_km).",
                },
                "longitude": {
                    "type": "number",
                    "description": "Longitude for radius search (requires latitude and max_radius_km).",
                },
                "max_radius_km": {
                    "type": "number",
                    "description": "Search radius in kilometres around lat/lon point.",
                },
                "min_latitude": {
                    "type": "number",
                    "description": "Min latitude for bounding box search.",
                },
                "max_latitude": {
                    "type": "number",
                    "description": "Max latitude for bounding box search.",
                },
                "min_longitude": {
                    "type": "number",
                    "description": "Min longitude for bounding box search.",
                },
                "max_longitude": {
                    "type": "number",
                    "description": "Max longitude for bounding box search.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max events to return (1-100). Default: 10.",
                },
                "order_by": {
                    "type": "string",
                    "enum": ["time", "time-asc", "magnitude", "magnitude-asc"],
                    "description": "Sort order. Default: 'time' (newest first).",
                },
            },
            "required": [],
        },
        handler=handle_query,
    )

    # ------------------------------------------------------------------
    # Tool 3: monitor — new significant earthquakes since last check
    # ------------------------------------------------------------------
    _state_file = (
        (agent_dir / "earthquake_seen.json")
        if agent_dir
        else Path("/tmp/earthquake_seen.json")
    )

    async def handle_monitor(args: dict[str, Any]) -> ToolResult:
        try:
            import urllib.parse
            from datetime import datetime, timezone, timedelta
            from .client import _format_ts, FDSN_BASE

            min_mag = float(args.get("min_magnitude", 6.0))
            lookback_hours = int(args.get("lookback_hours", 24))

            # Build time window: now - lookback_hours
            now = datetime.now(tz=timezone.utc)
            start = now - timedelta(hours=lookback_hours)
            start_str = start.strftime("%Y-%m-%dT%H:%M:%S")

            params = {
                "format": "geojson",
                "minmagnitude": min_mag,
                "starttime": start_str,
                "orderby": "time",
                "limit": 100,
            }
            url = f"{FDSN_BASE}?{urllib.parse.urlencode(params)}"
            data = await _async_fetch(url)
            all_features = [_format_feature(f) for f in data.get("features", [])]

            # Dedup
            seen = load_seen(_state_file)
            new_events, updated_seen = filter_new(all_features, seen)
            save_seen(_state_file, updated_seen)

            if not new_events:
                return ToolResult(content=f"No new M{min_mag}+ earthquakes since last check.")

            meta = data.get("metadata", {})
            header = (
                f"NEW M{min_mag}+ earthquakes since last check ({len(new_events)} event(s)):\n"
                f"Generated: {_format_ts(meta['generated']) if meta.get('generated') else 'N/A'}\n\n"
            )
            return ToolResult(content=header + _summarise(new_events, len(new_events)))

        except Exception as e:
            return ToolResult(content=f"Error checking new earthquakes: {e}", is_error=True)

    monitor_tool = Tool(
        name="check_new_earthquakes",
        description=(
            "Check for new earthquakes since the last time this tool was called. "
            "Uses exact float magnitude threshold via USGS FDSN API. "
            "Deduplicates across calls — only returns events not previously seen. "
            "Designed for heartbeat monitoring. Returns a quiet message if nothing new."
        ),
        parameters={
            "type": "object",
            "properties": {
                "min_magnitude": {
                    "type": "number",
                    "description": "Minimum magnitude (float). Default: 6.0.",
                },
                "lookback_hours": {
                    "type": "integer",
                    "description": (
                        "How many hours back to scan. Default: 24 "
                        "(wide window so nothing is missed during downtime)."
                    ),
                },
            },
            "required": [],
        },
        handler=handle_monitor,
    )

    return [recent_tool, query_tool, monitor_tool]
