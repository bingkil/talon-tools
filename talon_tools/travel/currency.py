"""
Currency conversion via frankfurter.app — free, no API key.
"""

from __future__ import annotations

import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode


_BASE_URL = "https://api.frankfurter.app"


def _get(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "talon-tools/1.0"})
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def convert(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert an amount between currencies."""
    params = urlencode({
        "amount": amount,
        "from": from_currency.upper(),
        "to": to_currency.upper(),
    })
    data = _get(f"{_BASE_URL}/latest?{params}")
    rates = data.get("rates", {})
    if not rates:
        return f"No conversion data for {from_currency} → {to_currency}."
    target = to_currency.upper()
    converted = rates.get(target)
    if converted is None:
        return f"Currency '{target}' not found. Available: {', '.join(sorted(rates.keys()))}"
    return f"{amount} {from_currency.upper()} = {converted} {target} (date: {data.get('date', 'unknown')})"


def list_currencies() -> str:
    """List all supported currencies."""
    data = _get(f"{_BASE_URL}/currencies")
    lines = [f"{code}: {name}" for code, name in sorted(data.items())]
    return "\n".join(lines)


def historical_rate(date: str, from_currency: str, to_currency: str) -> str:
    """Get exchange rate for a specific date (YYYY-MM-DD)."""
    params = urlencode({"from": from_currency.upper(), "to": to_currency.upper()})
    data = _get(f"{_BASE_URL}/{date}?{params}")
    rates = data.get("rates", {})
    target = to_currency.upper()
    rate = rates.get(target)
    if rate is None:
        return f"No rate found for {date}: {from_currency} → {to_currency}."
    return f"1 {from_currency.upper()} = {rate} {target} on {data.get('date', date)}"
