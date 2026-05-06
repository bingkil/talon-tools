"""Catholic daily mass readings — scrapes Universalis for the lectionary of the day."""

import json
import re
from datetime import date, datetime

import aiohttp

from talon_tools import Tool, ToolResult

_BASE_URL = "https://universalis.com"


def _readings_url(dt: date) -> str:
    """Build the Universalis mass readings URL for a given date."""
    return f"{_BASE_URL}/{dt.strftime('%Y%m%d')}/mass.htm"


async def _fetch_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as r:
            r.raise_for_status()
            return await r.text()


def _clean_text(html_fragment: str) -> str:
    """Strip tags and clean up whitespace from an HTML fragment."""
    text = re.sub(r"<br\s*/?>", "\n", html_fragment)
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    text = text.replace("&#160;", " ").replace("&nbsp;", " ")
    text = text.replace("&#8216;", "\u2018").replace("&#8217;", "\u2019")
    text = text.replace("&#8211;", "\u2013").replace("&#8220;", "\u201c").replace("&#8221;", "\u201d")
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&middot;", "\u00b7")
    # Normalize whitespace per line
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines if line)
    return text.strip()


def _extract_readings(html: str) -> dict:
    """Parse the Universalis mass page HTML into structured readings."""
    readings: dict = {}

    # Extract the liturgical day / feast name
    feast_match = re.search(r'<span id="feastname">(.*?)</span>', html, re.DOTALL)
    if feast_match:
        readings["title"] = _clean_text(feast_match.group(1))

    # Split into sections delimited by <hr class="shortrule"/>
    # Each section starts with a <table class="each"> containing the reading name + reference
    sections = re.split(r'<hr class="shortrule"\s*/?>', html)

    for section in sections:
        # Find the reading header table
        header_match = re.search(
            r'<table class="each"[^>]*>.*?<th align="left">(.*?)</th>.*?<th align="right">(.*?)</th>.*?</table>',
            section, re.DOTALL
        )
        if not header_match:
            # Try single-row format (psalm sometimes has reference on second row)
            header_match = re.search(
                r'<table class="each"[^>]*>.*?<th align="left">(.*?)</th>.*?</table>',
                section, re.DOTALL
            )
            if not header_match:
                continue
            heading = _clean_text(header_match.group(1))
            # Check for reference in a second <tr>
            ref_match = re.search(r'<th align="right">(.*?)</th>', section, re.DOTALL)
            reference = _clean_text(ref_match.group(1)) if ref_match else ""
        else:
            heading = _clean_text(header_match.group(1))
            reference = _clean_text(header_match.group(2))

        # Skip "Or:" alternative acclamation entries
        if heading.lower().startswith("or"):
            continue

        # Extract subtitle (h4 centered)
        subtitle_match = re.search(r'<h4[^>]*>(.*?)</h4>', section, re.DOTALL)
        subtitle = _clean_text(subtitle_match.group(1)) if subtitle_match else ""

        # Extract body text — all <div class="p|pi|v|vi|v gb"> elements after the table
        table_end = header_match.end()
        body_html = section[table_end:]
        # Remove audio clips
        body_html = re.sub(r'<div class="audioclip">.*?</div>', '', body_html, flags=re.DOTALL)
        # Extract text from the content divs
        div_texts = re.findall(
            r'<div class="(?:p|pi|v|vi|v gb|mai)[^"]*">(.*?)</div>',
            body_html, re.DOTALL
        )
        lines = [_clean_text(d) for d in div_texts if _clean_text(d)]
        # Strip copyright notice that appears at the end of the last reading
        text = "\n".join(l for l in lines if not l.startswith("Copyright"))

        # Categorize
        heading_lower = heading.lower()
        if "first reading" in heading_lower:
            key = "first_reading"
        elif "second reading" in heading_lower:
            key = "second_reading"
        elif "responsorial psalm" in heading_lower or "psalm" in heading_lower:
            key = "responsorial_psalm"
        elif "gospel acclamation" in heading_lower or "alleluia" in heading_lower:
            key = "gospel_acclamation"
        elif "gospel" in heading_lower:
            key = "gospel"
        else:
            key = heading_lower.replace(" ", "_")

        entry = {"heading": heading, "reference": reference, "text": text}
        if subtitle:
            entry["subtitle"] = subtitle
        readings[key] = entry

    return readings


async def _daily_readings(args: dict) -> ToolResult:
    """Fetch daily mass readings for a given date (or today)."""
    date_str = args.get("date")
    if date_str:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return ToolResult(json.dumps({"error": f"Invalid date format: {date_str}. Use YYYY-MM-DD."}))
    else:
        dt = date.today()

    url = _readings_url(dt)
    try:
        html = await _fetch_html(url)
    except Exception as e:
        return ToolResult(json.dumps({"error": f"Failed to fetch readings: {e}"}))

    readings = _extract_readings(html)
    readings["date"] = dt.isoformat()
    readings["url"] = url

    return ToolResult(json.dumps(readings, ensure_ascii=False))


def build_tools() -> list[Tool]:
    return [
        Tool(
            name="daily_mass_readings",
            description=(
                "Fetch Catholic daily mass readings from the liturgical calendar. "
                "Returns the First Reading, Responsorial Psalm, Second Reading "
                "(if applicable, e.g. Sundays/solemnities), Gospel Acclamation, "
                "and Gospel for the given date."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format. Defaults to today if omitted.",
                    },
                },
            },
            handler=_daily_readings,
        ),
    ]
