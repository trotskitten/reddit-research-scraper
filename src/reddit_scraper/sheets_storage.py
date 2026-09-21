"""Google Sheets dataset I/O layer.

The native Google Sheet is the canonical scraper destination. Existing rows are
read for deduplication and new Reddit posts are appended as new rows with blank
labeling and community-review fields. Existing rows are never rewritten by the scraper.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Iterable, Mapping

from google.oauth2 import service_account
from googleapiclient.discovery import build

SOURCE_COLUMNS = (
    "subreddit",
    "id",
    "title",
    "author",
    "created_utc",
    "created_iso",
    "url",
    "selftext",
)

LABEL_COLUMNS = (
    "batch_id",
    "label1",
    "label2",
    "label3",
    "validated_at",
)

REVIEW_COLUMNS = (
    "commentable",
)

DATASET_COLUMNS = SOURCE_COLUMNS + LABEL_COLUMNS + REVIEW_COLUMNS
DEFAULT_SHEET_NAME = "dataset"
SHEETS_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)


@dataclass(frozen=True)
class DatasetSnapshot:
    """Current canonical dataset rows read from Google Sheets."""

    rows: list[dict[str, str]]


def create_sheets_service():
    """Create an authenticated Google Sheets v4 service."""

    raw_credentials = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw_credentials:
        raise RuntimeError("Missing required environment variable: GOOGLE_SERVICE_ACCOUNT_JSON")

    try:
        credentials_info = json.loads(raw_credentials)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc

    credentials = service_account.Credentials.from_service_account_info(
        credentials_info,
        scopes=SHEETS_SCOPES,
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def get_dataset_spreadsheet_id() -> str:
    """Return the canonical Google Sheets spreadsheet ID."""

    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    if not spreadsheet_id:
        raise RuntimeError(
            "Missing required environment variable: GOOGLE_SHEETS_SPREADSHEET_ID"
        )
    return spreadsheet_id


def get_dataset_sheet_name() -> str:
    """Return the canonical dataset tab name."""

    return os.getenv("GOOGLE_SHEETS_SHEET_NAME", DEFAULT_SHEET_NAME)


def _sheet_range(sheet_name: str) -> str:
    escaped = sheet_name.replace("'", "''")
    return f"'{escaped}'!A:N"


def _cell_as_string(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def parse_sheet_values(values: list[list[object]]) -> list[dict[str, str]]:
    """Validate the 14-column header and normalize returned Sheet rows."""

    if not values:
        raise ValueError("Dataset sheet is empty; expected a header row")

    header = tuple(_cell_as_string(value) for value in values[0])
    if header != DATASET_COLUMNS:
        raise ValueError(
            "Unexpected dataset schema. "
            f"Expected {DATASET_COLUMNS}, received {header}."
        )

    rows: list[dict[str, str]] = []
    width = len(DATASET_COLUMNS)
    for source_row in values[1:]:
        normalized = [_cell_as_string(value) for value in source_row[:width]]
        normalized.extend([""] * (width - len(normalized)))
        rows.append(dict(zip(DATASET_COLUMNS, normalized, strict=True)))

    return rows


def read_dataset(service, spreadsheet_id: str, sheet_name: str | None = None) -> DatasetSnapshot:
    """Read all populated canonical dataset rows from Google Sheets."""

    resolved_sheet_name = sheet_name or get_dataset_sheet_name()
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=_sheet_range(resolved_sheet_name),
            valueRenderOption="FORMATTED_VALUE",
        )
        .execute()
    )
    return DatasetSnapshot(rows=parse_sheet_values(result.get("values", [])))


def prepare_rows_for_append(
    new_rows: Iterable[Mapping[str, object]],
) -> list[list[object]]:
    """Convert scraper rows to canonical 14-column Sheet rows.

    The scraper owns only the source columns. All labeling and community-review
    fields are deliberately appended blank so downstream workflows can fill them.
    """

    prepared: list[list[object]] = []

    for row in new_rows:
        missing = [column for column in SOURCE_COLUMNS if column not in row]
        if missing:
            raise ValueError(f"New dataset row is missing required columns: {missing}")

        source_values = [
            "" if row.get(column) is None else row.get(column)
            for column in SOURCE_COLUMNS
        ]
        prepared.append(
            source_values
            + [""] * len(LABEL_COLUMNS)
            + [""] * len(REVIEW_COLUMNS)
        )

    return prepared


def append_rows_to_sheet(
    service,
    spreadsheet_id: str,
    new_rows: Iterable[Mapping[str, object]],
    sheet_name: str | None = None,
    *,
    chunk_size: int = 100,
) -> int:
    """Append scraper rows without rewriting any existing Sheet cells."""

    prepared = prepare_rows_for_append(new_rows)
    if not prepared:
        return 0

    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")

    resolved_sheet_name = sheet_name or get_dataset_sheet_name()
    target_range = _sheet_range(resolved_sheet_name)
    appended = 0

    for start in range(0, len(prepared), chunk_size):
        chunk = prepared[start : start + chunk_size]
        response = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=target_range,
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"majorDimension": "ROWS", "values": chunk},
            )
            .execute()
        )
        updated_rows = int(response.get("updates", {}).get("updatedRows", 0))
        if updated_rows != len(chunk):
            raise RuntimeError(
                f"Google Sheets reported {updated_rows} appended rows; "
                f"expected {len(chunk)}"
            )
        appended += updated_rows

    return appended
