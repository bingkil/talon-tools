---
description: Monitor real-time earthquakes and search USGS seismic data worldwide
dependencies:
---

# Earthquake Monitor

Real-time earthquake monitoring via USGS. Fetch recent earthquakes from live feeds or run advanced parametric searches by magnitude, location, and time range.

## When to Use

- "Any earthquakes today?"
- "Recent earthquakes near Tokyo"
- "Show significant earthquakes this week"
- "Earthquakes above magnitude 5 in the last month"
- "Was there an earthquake in California?"
- Breaking news follow-up on seismic events

## Installation & Invocation

```bash
pip install talon-tools
```

No extra dependencies — uses Python stdlib only.

Load and call:

```python
import asyncio
from talon_tools.earthquake.tools import build_tools

tools = {t.name: t for t in build_tools()}
result = asyncio.run(tools["get_recent_earthquakes"].handler({"magnitude": "4.5", "period": "day"}))
print(result.content)
```

No credentials required.

### Without Python (curl)

```bash
# Recent M4.5+ earthquakes today
curl -s "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson" | jq '.features[:10] | .[] | {mag: .properties.mag, place: .properties.place, time: (.properties.time/1000 | todate)}'

# Significant earthquakes this week
curl -s "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson" | jq '.features[] | {mag: .properties.mag, place: .properties.place, time: (.properties.time/1000 | todate), alert: .properties.alert}'

# Search by region (lat/lon radius)
curl -s "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&minmagnitude=5&starttime=2026-05-01&latitude=35.68&longitude=139.76&maxradiuskm=500" | jq '.features[] | {mag: .properties.mag, place: .properties.place}'
```

Feed URL pattern: `https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{magnitude}_{period}.geojson`
- Magnitudes: `all`, `1.0`, `2.5`, `4.5`, `significant`
- Periods: `hour`, `day`, `week`, `month`

## Available Tools

| Tool | Purpose |
|------|---------|
| `get_recent_earthquakes` | Fetch recent earthquakes from USGS real-time feed |
| `query_earthquakes` | Advanced search by magnitude, location, and time range |
| `check_new_earthquakes` | Check for new earthquakes since last check (deduplicates seen events) |

## Workflow: Quick Check

1. `get_recent_earthquakes` with `magnitude=4.5` and `period=day` for notable events today
2. Review locations, depths, and alert levels

## Workflow: Regional Search

1. `query_earthquakes` with lat/lon center and radius to search a specific area
2. Filter by `min_magnitude` and time range for precision
3. Results include depth, alert level, and tsunami warnings

## Parameters

### get_recent_earthquakes
- `magnitude` — Filter level: `all`, `1.0`, `2.5`, `4.5`, or `significant`
- `period` — Time window: `hour`, `day`, `week`, or `month`
- `limit` — Max results (1–100)

### query_earthquakes
- `min_magnitude` / `max_magnitude` — Magnitude range
- `start_time` / `end_time` — ISO 8601 dates
- `latitude` / `longitude` / `max_radius_km` — Radius search
- `limit` — Max results
- `order_by` — Sort field

## Notes

- No API key required — uses public USGS data
- No dependencies — uses Python stdlib only
- Includes alert levels (green/yellow/orange/red) and tsunami warnings
- Deduplication built in to avoid re-reporting seen events
