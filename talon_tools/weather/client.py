"""
Open-Meteo weather client — free, no API key required.

Endpoints:
- Forecast: https://api.open-meteo.com/v1/forecast
- Geocoding: https://geocoding-api.open-meteo.com/v1/search
"""

from __future__ import annotations

import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode


_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


def _get(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "talon-tools/1.0"})
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def geocode(name: str, count: int = 5) -> str:
    """Resolve a place name to coordinates."""
    params = urlencode({"name": name, "count": count, "language": "en", "format": "json"})
    data = _get(f"{_GEOCODE_URL}?{params}")
    results = data.get("results", [])
    if not results:
        return f"No location found for '{name}'."
    lines = []
    for r in results:
        admin = r.get("admin1", "")
        country = r.get("country", "")
        loc = ", ".join(filter(None, [r["name"], admin, country]))
        lines.append(f"{loc} — lat={r['latitude']}, lon={r['longitude']}")
    return "\n".join(lines)


def forecast(
    latitude: float,
    longitude: float,
    days: int = 3,
    hourly: bool = False,
) -> str:
    """Get weather forecast for coordinates."""
    params: dict = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode,wind_speed_10m_max",
        "timezone": "auto",
        "forecast_days": min(days, 16),
    }
    if hourly:
        params["hourly"] = "temperature_2m,precipitation,weathercode,wind_speed_10m"

    url = f"{_FORECAST_URL}?{urlencode(params)}"
    data = _get(url)

    lines = []
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    for i, date in enumerate(dates):
        tmax = daily["temperature_2m_max"][i]
        tmin = daily["temperature_2m_min"][i]
        precip = daily["precipitation_sum"][i]
        wcode = daily["weathercode"][i]
        wind = daily["wind_speed_10m_max"][i]
        lines.append(
            f"{date}: {tmin}°C – {tmax}°C, precip {precip}mm, "
            f"wind {wind}km/h, code={wcode}"
        )

    if hourly and "hourly" in data:
        lines.append("\n--- Hourly (next 24h) ---")
        h = data["hourly"]
        for i in range(min(24, len(h.get("time", [])))):
            lines.append(
                f"  {h['time'][i]}: {h['temperature_2m'][i]}°C, "
                f"precip {h['precipitation'][i]}mm, wind {h['wind_speed_10m'][i]}km/h"
            )

    return "\n".join(lines) if lines else "No forecast data available."


def current_weather(latitude: float, longitude: float) -> str:
    """Get current weather conditions."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weathercode,wind_speed_10m,wind_direction_10m",
        "timezone": "auto",
    }
    url = f"{_FORECAST_URL}?{urlencode(params)}"
    data = _get(url)
    cur = data.get("current", {})
    if not cur:
        return "No current weather data available."
    return (
        f"Temperature: {cur.get('temperature_2m')}°C (feels like {cur.get('apparent_temperature')}°C)\n"
        f"Humidity: {cur.get('relative_humidity_2m')}%\n"
        f"Precipitation: {cur.get('precipitation')}mm\n"
        f"Wind: {cur.get('wind_speed_10m')}km/h from {cur.get('wind_direction_10m')}°\n"
        f"Weather code: {cur.get('weathercode')}"
    )
