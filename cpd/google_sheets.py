"""Queries Google Sheets directly via Google's no-key JSON data API.

Neither a manual download nor any Google Cloud credential is needed. The only
requirement is that each spreadsheet is shared with
"Anyone with the link -> Viewer" (Share button in the sheet).

We use the Google Visualization (gviz) query endpoint, which returns the tab
contents as JSON straight from the live sheet, then turn each response tab
into a pandas DataFrame for the normal CPD parsing pipeline.

Only the spreadsheet ID(s) need to be configured in ``.env``:

    GOOGLE_SHEET_ID=...              # registration form responses
    GOOGLE_SHEET_PICKUP_ID=...       # optional: separate pickup form responses
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_SHEET_NAMES = [
    "Form Responses 1",
    "Form Responses 2",
    "Form Responses 3",
    "Sheet1",
    "Sheet2",
]


def _extract_json(text: str) -> dict:
    """Pull the JSON payload out of the gviz ``setResponse(...)`` wrapper."""
    match = re.search(r"setResponse\((\{.*\})\)\s*;?\s*$", text, re.S)
    if not match:
        raise ValueError("Response from Google Sheets was not a data query")
    return json.loads(match.group(1))


def _fetch_sheet(
    spreadsheet_id: str, sheet_name: str, timeout: int = 30
) -> pd.DataFrame:
    url = (
        "https://docs.google.com/spreadsheets/d/"
        f"{spreadsheet_id}/gviz/tq?sheet={quote(sheet_name)}&tqx=out:json"
    )
    req = Request(url, headers={"User-Agent": "cpd-track"})
    with urlopen(req, timeout=timeout) as resp:
        payload = _extract_json(resp.read().decode("utf-8", "replace"))

    if payload.get("status") == "error":
        raise ValueError(f"Google Sheets error: {payload.get('errors')}")
    table = payload.get("table", {})
    cols = [c.get("label", "") or "" for c in table.get("cols", [])]
    rows = [
        [c.get("v") if c else None for c in row.get("c", [])]
        for row in table.get("rows", [])
    ]

    df = pd.DataFrame(rows, columns=cols)
    df.columns = [str(c) for c in df.columns]
    return df


def fetch_tabs(
    spreadsheet_id: str,
    sheet_names: list[str] | None = None,
    timeout: int = 30,
) -> dict[str, pd.DataFrame]:
    """Fetch every requested tab of a spreadsheet as DataFrames.

    Returns a dict mapping ``spreadsheet_id__sheet_name`` -> DataFrame.
    Tabs that cannot be fetched (wrong name, not shared) are skipped with a
    warning. Column labels are the raw Google Form question text.
    """
    result: dict[str, pd.DataFrame] = {}
    for name in sheet_names or DEFAULT_SHEET_NAMES:
        try:
            result[f"{spreadsheet_id}__{name}"] = _fetch_sheet(
                spreadsheet_id, name, timeout
            )
        except Exception as exc:  # noqa: BLE001 - a missing tab is normal
            logger.info("Tab '%s' of %s not available: %s", name, spreadsheet_id, exc)
    return result