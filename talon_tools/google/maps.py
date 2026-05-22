"""
Google Maps / Places API client.

Requires: GOOGLE_MAPS_API_KEY environment variable.
Enable Maps JavaScript API, Places API, Directions API, and Geocoding API
in Google Cloud Console.
"""

from __future__ import annotations

import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode

from talon_tools.credentials import get as cred


GOOGLE_MAPS_API_KEY = "GOOGLE_MAPS_API_KEY"

_MAPS_BASE = "https://maps.googleapis.com/maps/api"


def _get_api_key() -> str:
    key = cred(GOOGLE_MAPS_API_KEY, "")
    if not key:
        raise RuntimeError(f"{GOOGLE_MAPS_API_KEY} not set.")
    return key


def _get(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "talon-tools/1.0"})
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def geocode(address: str) -> str:
    """Geocode an address to coordinates."""
    params = urlencode({"address": address, "key": _get_api_key()})
    data = _get(f"{_MAPS_BASE}/geocode/json?{params}")
    results = data.get("results", [])
    if not results:
        return f"No results for '{address}'."
    lines = []
    for r in results[:3]:
        addr = r.get("formatted_address", "")
        loc = r["geometry"]["location"]
        lines.append(f"{addr} — lat={loc['lat']}, lng={loc['lng']}")
    return "\n".join(lines)


def reverse_geocode(latitude: float, longitude: float) -> str:
    """Reverse geocode coordinates to an address."""
    params = urlencode({"latlng": f"{latitude},{longitude}", "key": _get_api_key()})
    data = _get(f"{_MAPS_BASE}/geocode/json?{params}")
    results = data.get("results", [])
    if not results:
        return f"No address found for ({latitude}, {longitude})."
    return results[0].get("formatted_address", "Unknown")


def directions(origin: str, destination: str, mode: str = "driving") -> str:
    """Get directions between two locations."""
    params = urlencode({
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "key": _get_api_key(),
    })
    data = _get(f"{_MAPS_BASE}/directions/json?{params}")
    routes = data.get("routes", [])
    if not routes:
        return f"No route found: {origin} → {destination} ({mode})."

    route = routes[0]
    leg = route["legs"][0]
    distance = leg["distance"]["text"]
    duration = leg["duration"]["text"]

    steps = []
    for s in leg["steps"][:15]:
        instruction = s.get("html_instructions", "").replace("<b>", "").replace("</b>", "").replace("<div>", " ").replace("</div>", "")
        # Strip remaining HTML tags
        import re
        instruction = re.sub(r"<[^>]+>", "", instruction)
        step_dist = s["distance"]["text"]
        steps.append(f"  • {instruction} ({step_dist})")

    header = f"{origin} → {destination}\nDistance: {distance} | Duration: {duration} | Mode: {mode}"
    return header + "\n\nSteps:\n" + "\n".join(steps)


def places_nearby(
    latitude: float,
    longitude: float,
    radius: int = 1000,
    place_type: str | None = None,
    keyword: str | None = None,
) -> str:
    """Search for places near a location."""
    params: dict = {
        "location": f"{latitude},{longitude}",
        "radius": radius,
        "key": _get_api_key(),
    }
    if place_type:
        params["type"] = place_type
    if keyword:
        params["keyword"] = keyword

    data = _get(f"{_MAPS_BASE}/place/nearbysearch/json?{urlencode(params)}")
    results = data.get("results", [])
    if not results:
        return "No places found nearby."

    lines = []
    for p in results[:10]:
        name = p.get("name", "Unknown")
        rating = p.get("rating", "N/A")
        vicinity = p.get("vicinity", "")
        open_now = p.get("opening_hours", {}).get("open_now")
        status = " [OPEN]" if open_now else (" [CLOSED]" if open_now is False else "")
        lines.append(f"{name} — ★{rating}{status} | {vicinity}")

    return "\n".join(lines)


def distance_matrix(origins: str, destinations: str, mode: str = "driving") -> str:
    """Get travel distance and time between multiple origins and destinations."""
    params = urlencode({
        "origins": origins,
        "destinations": destinations,
        "mode": mode,
        "key": _get_api_key(),
    })
    data = _get(f"{_MAPS_BASE}/distancematrix/json?{params}")

    origin_addrs = data.get("origin_addresses", [])
    dest_addrs = data.get("destination_addresses", [])
    rows = data.get("rows", [])

    lines = []
    for i, row in enumerate(rows):
        for j, elem in enumerate(row.get("elements", [])):
            if elem.get("status") != "OK":
                lines.append(f"{origin_addrs[i]} → {dest_addrs[j]}: {elem.get('status', 'UNKNOWN')}")
            else:
                dist = elem["distance"]["text"]
                dur = elem["duration"]["text"]
                lines.append(f"{origin_addrs[i]} → {dest_addrs[j]}: {dist}, {dur}")

    return "\n".join(lines) if lines else "No distance data available."
