"""
Google Sheets integration — read, write, and manage spreadsheets.

Sync functions — wrap in run_in_executor() for async.
"""

from __future__ import annotations

from googleapiclient.discovery import build

from .auth import get_credentials


def _service(token_file=None):
    return build("sheets", "v4", credentials=get_credentials(token_file))


def read_sheet(spreadsheet_id: str, range: str = "Sheet1", token_file=None) -> str:
    """Read values from a spreadsheet range (e.g. 'Sheet1!A1:D10' or just 'Sheet1')."""
    svc = _service(token_file)
    result = svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=range,
    ).execute()

    rows = result.get("values", [])
    if not rows:
        return "No data found."

    # Format as a readable table
    lines = []
    for i, row in enumerate(rows):
        line = " | ".join(str(c) for c in row)
        lines.append(line)
        if i == 0:
            lines.append("-" * len(line))

    return "\n".join(lines)


def write_sheet(
    spreadsheet_id: str,
    range: str,
    values: list[list[str]],
    mode: str = "overwrite",
    token_file=None,
) -> str:
    """Write values to a spreadsheet range.

    Args:
        spreadsheet_id: The spreadsheet ID.
        range: Target range (e.g. 'Sheet1!A1').
        values: 2D array of values to write.
        mode: 'overwrite' (RAW) or 'append' to add after existing data.
    """
    svc = _service(token_file)
    body = {"values": values}

    if mode == "append":
        result = svc.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()
        updated = result.get("updates", {}).get("updatedRows", 0)
        return f"Appended {updated} rows."
    else:
        result = svc.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueInputOption="USER_ENTERED",
            body=body,
        ).execute()
        updated = result.get("updatedCells", 0)
        return f"Updated {updated} cells."


def clear_sheet(spreadsheet_id: str, range: str, token_file=None) -> str:
    """Clear values from a spreadsheet range."""
    svc = _service(token_file)
    svc.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id, range=range, body={},
    ).execute()
    return f"Cleared {range}."


def get_spreadsheet_info(spreadsheet_id: str, token_file=None) -> str:
    """Get spreadsheet metadata — title and sheet names."""
    svc = _service(token_file)
    meta = svc.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="properties.title,sheets.properties",
    ).execute()

    title = meta.get("properties", {}).get("title", "?")
    sheets = meta.get("sheets", [])
    sheet_names = [s["properties"]["title"] for s in sheets]

    lines = [f"Spreadsheet: {title}"]
    for name in sheet_names:
        lines.append(f"  - {name}")
    return "\n".join(lines)


def create_spreadsheet(title: str, sheet_names: list[str] | None = None, token_file=None) -> str:
    """Create a new spreadsheet. Returns its ID and URL."""
    svc = _service(token_file)
    body: dict = {"properties": {"title": title}}
    if sheet_names:
        body["sheets"] = [
            {"properties": {"title": name}} for name in sheet_names
        ]

    result = svc.spreadsheets().create(body=body).execute()
    sid = result["spreadsheetId"]
    url = result["spreadsheetUrl"]
    return f"Created spreadsheet: {title}\nID: {sid}\nURL: {url}"
