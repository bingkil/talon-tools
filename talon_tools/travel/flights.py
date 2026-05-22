"""
Kiwi/Tequila flight search API client.

Requires: KIWI_API_KEY environment variable (get from https://tequila.kiwi.com)
"""

from __future__ import annotations

import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode

from talon_tools.credentials import get as cred


KIWI_API_KEY = "KIWI_API_KEY"

_BASE_URL = "https://api.tequila.kiwi.com"


def _get_api_key() -> str:
    key = cred(KIWI_API_KEY, "")
    if not key:
        raise RuntimeError(f"{KIWI_API_KEY} not set. Get one at https://tequila.kiwi.com")
    return key


def _get(endpoint: str, params: dict) -> dict:
    url = f"{_BASE_URL}{endpoint}?{urlencode(params)}"
    req = Request(url, headers={
        "apikey": _get_api_key(),
        "User-Agent": "talon-tools/1.0",
    })
    with urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def search_flights(
    fly_from: str,
    fly_to: str,
    date_from: str,
    date_to: str | None = None,
    return_from: str | None = None,
    return_to: str | None = None,
    adults: int = 1,
    max_results: int = 5,
    curr: str = "USD",
    sort: str = "price",
    max_stopovers: int | None = None,
) -> str:
    """Search for flights between locations.

    Args:
        fly_from: Origin IATA code or city (e.g. 'LHR', 'London')
        fly_to: Destination IATA code or city
        date_from: Departure date (DD/MM/YYYY)
        date_to: Latest departure date (DD/MM/YYYY), defaults to date_from
        return_from: Return date from (DD/MM/YYYY) for round-trip
        return_to: Return date to (DD/MM/YYYY) for round-trip
        adults: Number of passengers
        max_results: Maximum results to return
        curr: Currency for prices
        sort: Sort by 'price', 'duration', or 'quality'
        max_stopovers: Maximum stopovers (0 = direct only)
    """
    params: dict = {
        "fly_from": fly_from,
        "fly_to": fly_to,
        "date_from": date_from,
        "date_to": date_to or date_from,
        "adults": adults,
        "limit": max_results,
        "curr": curr.upper(),
        "sort": sort,
    }
    if return_from:
        params["return_from"] = return_from
    if return_to:
        params["return_to"] = return_to
    if max_stopovers is not None:
        params["max_stopovers"] = max_stopovers

    data = _get("/v2/search", params)
    flights = data.get("data", [])
    if not flights:
        return f"No flights found: {fly_from} → {fly_to} on {date_from}."

    lines = []
    for f in flights[:max_results]:
        price = f.get("price", "?")
        duration_h = f.get("duration", {}).get("total", 0) // 3600
        duration_m = (f.get("duration", {}).get("total", 0) % 3600) // 60
        airlines = ", ".join(set(r.get("airline", "") for r in f.get("route", [])))
        stops = len(f.get("route", [])) - 1
        dep = f.get("local_departure", "")[:16]
        arr = f.get("local_arrival", "")[:16]
        deep_link = f.get("deep_link", "")

        line = (
            f"{dep} → {arr} | {duration_h}h{duration_m}m | "
            f"{stops} stop{'s' if stops != 1 else ''} | "
            f"{airlines} | {price} {curr.upper()}"
        )
        if deep_link:
            line += f"\n  Book: {deep_link}"
        lines.append(line)

    return "\n\n".join(lines)


def search_locations(query: str, locale: str = "en-US") -> str:
    """Search for airport/city IATA codes."""
    params = {"term": query, "locale": locale, "location_types": "city,airport", "limit": 5}
    data = _get("/locations/query", params)
    locations = data.get("locations", [])
    if not locations:
        return f"No locations found for '{query}'."
    lines = []
    for loc in locations:
        code = loc.get("code", "?")
        name = loc.get("name", "?")
        country = loc.get("country", {}).get("name", "?")
        ltype = loc.get("type", "?")
        lines.append(f"{code} — {name}, {country} ({ltype})")
    return "\n".join(lines)
