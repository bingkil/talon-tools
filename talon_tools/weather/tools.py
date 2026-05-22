"""Weather tool definitions for LLM agents — powered by Open-Meteo (free, no API key)."""

from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path
from typing import Any

from talon_tools import Tool, ToolResult
from .client import geocode, forecast, current_weather


REQUIRED_CREDENTIALS: dict[str, str] = {}


def required_credentials() -> dict[str, str]:
    """Return credential keys this tool bundle needs, mapped to signup URLs."""
    return REQUIRED_CREDENTIALS


async def _run(fn, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(fn, **kwargs))


def build_tools(agent_dir: Path | None = None, **_kwargs) -> list[Tool]:
    """Return weather tools."""

    async def handle_geocode(args: dict[str, Any]) -> ToolResult:
        try:
            result = await _run(geocode, name=args["name"], count=args.get("count", 5))
            return ToolResult(content=result)
        except Exception as e:
            return ToolResult(content=f"Geocoding error: {e}", is_error=True)

    async def handle_forecast(args: dict[str, Any]) -> ToolResult:
        try:
            result = await _run(
                forecast,
                latitude=float(args["latitude"]),
                longitude=float(args["longitude"]),
                days=int(args.get("days", 3)),
                hourly=args.get("hourly", False),
            )
            return ToolResult(content=result)
        except Exception as e:
            return ToolResult(content=f"Forecast error: {e}", is_error=True)

    async def handle_current(args: dict[str, Any]) -> ToolResult:
        try:
            result = await _run(
                current_weather,
                latitude=float(args["latitude"]),
                longitude=float(args["longitude"]),
            )
            return ToolResult(content=result)
        except Exception as e:
            return ToolResult(content=f"Current weather error: {e}", is_error=True)

    return [
        Tool(
            name="weather_geocode",
            description=(
                "Resolve a city/place name to geographic coordinates (latitude, longitude). "
                "Use this first to get coordinates before calling weather_forecast or weather_current."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "City or place name to look up (e.g. 'London', 'Tokyo', 'New York')"},
                    "count": {"type": "integer", "description": "Max results to return (1-10). Default: 5."},
                },
                "required": ["name"],
            },
            handler=handle_geocode,
        ),
        Tool(
            name="weather_forecast",
            description=(
                "Get weather forecast for a location. Provides daily min/max temperature, "
                "precipitation, wind speed, and weather codes. Optionally includes hourly data. "
                "Use weather_geocode first to get coordinates."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "description": "Latitude of the location"},
                    "longitude": {"type": "number", "description": "Longitude of the location"},
                    "days": {"type": "integer", "description": "Number of forecast days (1-16). Default: 3."},
                    "hourly": {"type": "boolean", "description": "Include hourly breakdown for next 24h. Default: false."},
                },
                "required": ["latitude", "longitude"],
            },
            handler=handle_forecast,
        ),
        Tool(
            name="weather_current",
            description=(
                "Get current weather conditions at a location — temperature, humidity, "
                "precipitation, wind speed and direction. Use weather_geocode first to get coordinates."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "description": "Latitude of the location"},
                    "longitude": {"type": "number", "description": "Longitude of the location"},
                },
                "required": ["latitude", "longitude"],
            },
            handler=handle_current,
        ),
    ]
