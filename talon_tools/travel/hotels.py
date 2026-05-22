"""
Hotelbeds hotel search API client.

Requires: HOTELBEDS_API_KEY and HOTELBEDS_SECRET environment variables.
Get from: https://developer.hotelbeds.com (free eval: 50 req/day)
"""

from __future__ import annotations

import hashlib
import json
import time
from urllib.request import urlopen, Request

from talon_tools.credentials import get as cred


HOTELBEDS_API_KEY = "HOTELBEDS_API_KEY"
HOTELBEDS_SECRET = "HOTELBEDS_SECRET"

_BASE_URL = "https://api.test.hotelbeds.com/hotel-api/1.0"


def _get_credentials() -> tuple[str, str]:
    key = cred(HOTELBEDS_API_KEY, "")
    secret = cred(HOTELBEDS_SECRET, "")
    if not key or not secret:
        raise RuntimeError(
            f"{HOTELBEDS_API_KEY} and {HOTELBEDS_SECRET} not set. "
            "Get them at https://developer.hotelbeds.com"
        )
    return key, secret


def _signature(key: str, secret: str) -> str:
    """Generate X-Signature header (SHA256 of key+secret+timestamp)."""
    ts = str(int(time.time()))
    raw = key + secret + ts
    return hashlib.sha256(raw.encode()).hexdigest()


def _post(endpoint: str, body: dict) -> dict:
    key, secret = _get_credentials()
    url = f"{_BASE_URL}{endpoint}"
    data = json.dumps(body).encode()
    req = Request(url, data=data, method="POST", headers={
        "Api-key": key,
        "X-Signature": _signature(key, secret),
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "talon-tools/1.0",
    })
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def search_hotels(
    destination_code: str,
    check_in: str,
    check_out: str,
    adults: int = 2,
    rooms: int = 1,
    max_results: int = 5,
    currency: str = "USD",
) -> str:
    """Search for available hotels.

    Args:
        destination_code: Hotelbeds destination code (use 'MCO' for Orlando, 'LON' for London, etc.)
        check_in: Check-in date (YYYY-MM-DD)
        check_out: Check-out date (YYYY-MM-DD)
        adults: Number of adults per room
        rooms: Number of rooms
        max_results: Maximum hotels to return
        currency: Price currency
    """
    body = {
        "stay": {"checkIn": check_in, "checkOut": check_out},
        "occupancies": [{"rooms": rooms, "adults": adults, "children": 0}],
        "destination": {"code": destination_code},
        "filter": {"maxHotels": max_results},
        "currency": currency.upper(),
    }
    data = _post("/hotels", body)
    hotels_data = data.get("hotels", {}).get("hotels", [])
    if not hotels_data:
        return f"No hotels found in {destination_code} for {check_in} to {check_out}."

    lines = []
    for h in hotels_data[:max_results]:
        name = h.get("name", "Unknown")
        category = h.get("categoryName", "")
        min_rate = h.get("minRate", "?")
        max_rate = h.get("maxRate", "?")
        zone = h.get("zoneName", "")
        lines.append(
            f"{name} ({category}) — {min_rate}–{max_rate} {currency.upper()}"
            + (f" | {zone}" if zone else "")
        )

    return "\n".join(lines)
