"""Google Drive dataset I/O layer.

This module downloads the canonical CSV dataset, parses it for deduplication,
appends new rows without rewriting historical CSV rows, and replaces the same
Drive file with the updated bytes.
"""

from __future__ import annotations

import csv
import io
import json
import os
from dataclasses import dataclass
from typing import Iterable

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

DATASET_COLUMNS = (
    "subreddit",
    "id",
    "title",
    "author",
    "created_utc",
    "created_iso",
    "url",
    "selftext",
)

DRIVE_SCOPES = ("https://www.googleapis.com/auth/drive",)


@dataclass(frozen=True)
class DatasetSnapshot:
    """A downloaded dataset represented as both raw bytes and parsed rows."""

    raw_bytes: bytes
    rows: list[dict[str, str]]


def create_drive_service():
    """Create an authenticated Google Drive v3 service from environment JSON.

    Required environment variable:
    - GOOGLE_SERVICE_ACCOUNT_JSON: complete service-account JSON object
    """

    raw_credentials = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw_credentials:
        raise RuntimeError("Missing required environment variable: GOOGLE_SERVICE_ACCOUNT_JSON")

    try:
        credentials_info = json.loads(raw_credentials)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc

    credentials = service_account.Credentials.from_service_account_info(
        credentials_info,
        scopes=DRIVE_SCOPES,
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def get_dataset_file_id() -> str:
    """Return the canonical Drive dataset file ID from the environment."""

    file_id = os.getenv("GOOGLE_DRIVE_FILE_ID")
    if not file_id:
        raise RuntimeError("Missing required environment variable: GOOGLE_DRIVE_FILE_ID")
    return file_id


def parse_dataset_csv(raw_bytes: bytes) -> list[dict[str, str]]:
    """Parse canonical dataset bytes and verify the expected eight-column schema."""

    text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))

    fieldnames = tuple(reader.fieldnames or ())
    if fieldnames != DATASET_COLUMNS:
        raise ValueError(
            "Unexpected dataset schema. "
            f"Expected {DATASET_COLUMNS}, received {fieldnames}."
        )

    return [dict(row) for row in reader]


def download_dataset(service, file_id: str) -> DatasetSnapshot:
    """Download the current CSV dataset from Google Drive."""

    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    raw_bytes = buffer.getvalue()
    return DatasetSnapshot(raw_bytes=raw_bytes, rows=parse_dataset_csv(raw_bytes))


def _line_terminator(raw_bytes: bytes) -> str:
    """Preserve the existing CSV newline convention when appending rows."""

    first_line_end = raw_bytes.find(b"\n")
    if first_line_end > 0 and raw_bytes[first_line_end - 1 : first_line_end] == b"\r":
        return "\r\n"
    return "\n"


def append_rows_to_csv_bytes(
    raw_bytes: bytes,
    new_rows: Iterable[dict[str, object]],
) -> bytes:
    """Append canonical rows while preserving all existing dataset bytes.

    No header is added because the downloaded dataset already contains one.
    Extra transient fields, such as matcher metadata, are ignored.
    """

    rows = list(new_rows)
    if not rows:
        return raw_bytes

    # Validate the existing dataset before constructing replacement bytes.
    parse_dataset_csv(raw_bytes)

    line_terminator = _line_terminator(raw_bytes)
    append_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        append_buffer,
        fieldnames=DATASET_COLUMNS,
        extrasaction="ignore",
        lineterminator=line_terminator,
    )

    for row in rows:
        missing = [column for column in DATASET_COLUMNS if column not in row]
        if missing:
            raise ValueError(f"New dataset row is missing required columns: {missing}")
        writer.writerow(row)

    separator = b"" if raw_bytes.endswith((b"\n", b"\r")) else line_terminator.encode("utf-8")
    return raw_bytes + separator + append_buffer.getvalue().encode("utf-8")


def upload_dataset(service, file_id: str, raw_bytes: bytes) -> None:
    """Replace the canonical Drive CSV content while preserving its file ID."""

    media = MediaIoBaseUpload(
        io.BytesIO(raw_bytes),
        mimetype="text/csv",
        resumable=False,
    )
    service.files().update(fileId=file_id, media_body=media).execute()
