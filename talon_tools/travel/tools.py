"""Travel tool definitions for LLM agents — flights, hotels, and currency."""

from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path
from typing import Any

from talon_tools import Tool, ToolResult
from .flights import search_flights, search_locations, KIWI_API_KEY
from .hotels import search_hotels, HOTELBEDS_API_KEY, HOTELBEDS_SECRET
from .currency import convert, list_currencies, historical_rate


REQUIRED_CREDENTIALS = {
    KIWI_API_KEY: "https://tequila.kiwi.com",
    HOTELBEDS_API_KEY: "https://developer.hotelbeds.com",
    HOTELBEDS_SECRET: "https://developer.hotelbeds.com",
}


def required_credentials() -> dict[str, str]:
    """Return credential keys this tool bundle needs, mapped to signup URLs."""
    return REQUIRED_CREDENTIALS


async def _run(fn, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(fn, **kwargs))


def build_tools(agent_dir: Path | None = None, **_kwargs) -> list[Tool]:
    """Return travel tools (flights, hotels, currency)."""

    # -- Flights (Kiwi/Tequila) --

    async def handle_search_flights(args: dict[str, Any]) -> ToolResult:
        try:
            result = await _run(
                search_flights,
                fly_from=args["fly_from"],
                fly_to=args["fly_to"],
                date_from=args["date_from"],
                date_to=args.get("date_to"),
                return_from=args.get("return_from"),
                return_to=args.get("return_to"),
                adults=int(args.get("adults", 1)),
                max_results=int(args.get("max_results", 5)),
                curr=args.get("currency", "USD"),
                sort=args.get("sort", "price"),
                max_stopovers=args.get("max_stopovers"),
            )
            return ToolResult(content=result)
        except Exception as e:
            return ToolResult(content=f"Flight search error: {e}", is_error=True)

    async def handle_search_locations(args: dict[str, Any]) -> ToolResult:
        try:
            result = await _run(search_locations, query=args["query"])
            return ToolResult(content=result)
        except Exception as e:
            return ToolResult(content=f"Location search error: {e}", is_error=True)

    # -- Hotels (Hotelbeds) --

    async def handle_search_hotels(args: dict[str, Any]) -> ToolResult:
        try:
            result = await _run(
                search_hotels,
                destination_code=args["destination_code"],
                check_in=args["check_in"],
                check_out=args["check_out"],
                adults=int(args.get("adults", 2)),
                rooms=int(args.get("rooms", 1)),
                max_results=int(args.get("max_results", 5)),
                currency=args.get("currency", "USD"),
            )
            return ToolResult(content=result)
        except Exception as e:
            return ToolResult(content=f"Hotel search error: {e}", is_error=True)

    # -- Currency (frankfurter.app) --

    async def handle_convert(args: dict[str, Any]) -> ToolResult:
        try:
            result = await _run(
                convert,
                amount=float(args["amount"]),
                from_currency=args["from"],
                to_currency=args["to"],
            )
            return ToolResult(content=result)
        except Exception as e:
            return ToolResult(content=f"Currency conversion error: {e}", is_error=True)

    async def handle_list_currencies(args: dict[str, Any]) -> ToolResult:
        try:
            result = await _run(list_currencies)
            return ToolResult(content=result)
        except Exception as e:
            return ToolResult(content=f"Error listing currencies: {e}", is_error=True)

    async def handle_historical_rate(args: dict[str, Any]) -> ToolResult:
        try:
            result = await _run(
                historical_rate,
                date=args["date"],
                from_currency=args["from"],
                to_currency=args["to"],
            )
            return ToolResult(content=result)
        except Exception as e:
            return ToolResult(content=f"Historical rate error: {e}", is_error=True)

    return [
        # --- Flights ---
        Tool(
            name="flight_search",
            description=(
                "Search for flights between cities/airports. Returns prices, duration, stops, "
                "and booking links. Use flight_location_search first to find IATA codes if needed. "
                "Requires KIWI_API_KEY."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "fly_from": {"type": "string", "description": "Origin IATA code or city name (e.g. 'LHR', 'LON', 'London')"},
                    "fly_to": {"type": "string", "description": "Destination IATA code or city name"},
                    "date_from": {"type": "string", "description": "Earliest departure date (DD/MM/YYYY)"},
                    "date_to": {"type": "string", "description": "Latest departure date (DD/MM/YYYY). Defaults to date_from."},
                    "return_from": {"type": "string", "description": "Return date from (DD/MM/YYYY) for round-trip. Omit for one-way."},
                    "return_to": {"type": "string", "description": "Return date to (DD/MM/YYYY) for round-trip."},
                    "adults": {"type": "integer", "description": "Number of passengers. Default: 1."},
                    "max_results": {"type": "integer", "description": "Max results (1-20). Default: 5."},
                    "currency": {"type": "string", "description": "Price currency (ISO 4217). Default: USD."},
                    "sort": {"type": "string", "enum": ["price", "duration", "quality"], "description": "Sort results by. Default: price."},
                    "max_stopovers": {"type": "integer", "description": "Maximum stopovers. 0 = direct flights only."},
                },
                "required": ["fly_from", "fly_to", "date_from"],
            },
            handler=handle_search_flights,
            requires_credentials=[KIWI_API_KEY],
        ),
        Tool(
            name="flight_location_search",
            description=(
                "Find airport/city IATA codes for use with flight_search. "
                "Returns matching airports and cities with their codes."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "City or airport name to search (e.g. 'Bali', 'Tokyo Narita')"},
                },
                "required": ["query"],
            },
            handler=handle_search_locations,
            requires_credentials=[KIWI_API_KEY],
        ),
        # --- Hotels ---
        Tool(
            name="hotel_search",
            description=(
                "Search for available hotels at a destination. Returns hotel names, categories, "
                "and price ranges. Requires HOTELBEDS_API_KEY and HOTELBEDS_SECRET."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "destination_code": {"type": "string", "description": "Hotelbeds destination code (e.g. 'LON' for London, 'PMI' for Palma de Mallorca)"},
                    "check_in": {"type": "string", "description": "Check-in date (YYYY-MM-DD)"},
                    "check_out": {"type": "string", "description": "Check-out date (YYYY-MM-DD)"},
                    "adults": {"type": "integer", "description": "Adults per room. Default: 2."},
                    "rooms": {"type": "integer", "description": "Number of rooms. Default: 1."},
                    "max_results": {"type": "integer", "description": "Max hotels to return. Default: 5."},
                    "currency": {"type": "string", "description": "Price currency. Default: USD."},
                },
                "required": ["destination_code", "check_in", "check_out"],
            },
            handler=handle_search_hotels,
            requires_credentials=[HOTELBEDS_API_KEY, HOTELBEDS_SECRET],
        ),
        # --- Currency ---
        Tool(
            name="currency_convert",
            description=(
                "Convert an amount from one currency to another using live exchange rates. "
                "Free, no API key needed."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "Amount to convert"},
                    "from": {"type": "string", "description": "Source currency code (e.g. 'USD', 'EUR', 'GBP')"},
                    "to": {"type": "string", "description": "Target currency code"},
                },
                "required": ["amount", "from", "to"],
            },
            handler=handle_convert,
        ),
        Tool(
            name="currency_list",
            description="List all supported currencies for conversion.",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=handle_list_currencies,
        ),
        Tool(
            name="currency_historical",
            description="Get the exchange rate for a specific historical date.",
            parameters={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date to look up (YYYY-MM-DD)"},
                    "from": {"type": "string", "description": "Source currency code"},
                    "to": {"type": "string", "description": "Target currency code"},
                },
                "required": ["date", "from", "to"],
            },
            handler=handle_historical_rate,
        ),
    ]
