import csv
import io

import pytest

from reddit_scraper.drive_storage import (
    DATASET_COLUMNS,
    append_rows_to_csv_bytes,
    parse_dataset_csv,
)


def make_csv(rows, lineterminator="\n"):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=DATASET_COLUMNS, lineterminator=lineterminator)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def sample_row(post_id="abc123", selftext="Body text"):
    return {
        "subreddit": "projectmanagement",
        "id": post_id,
        "title": "Example title",
        "author": "example_user",
        "created_utc": 1788436800.0,
        "created_iso": "2026-09-03T12:00:00+00:00",
        "url": f"https://www.reddit.com/comments/{post_id}/",
        "selftext": selftext,
    }


def test_parse_dataset_csv_returns_rows():
    raw = make_csv([sample_row()])

    rows = parse_dataset_csv(raw)

    assert len(rows) == 1
    assert rows[0]["id"] == "abc123"
    assert rows[0]["selftext"] == "Body text"


def test_parse_dataset_csv_rejects_unexpected_schema():
    raw = b"id,title\nabc,Example\n"

    with pytest.raises(ValueError, match="Unexpected dataset schema"):
        parse_dataset_csv(raw)


def test_append_preserves_existing_bytes_exactly():
    original = make_csv([sample_row("old")])

    updated = append_rows_to_csv_bytes(original, [sample_row("new")])

    assert updated.startswith(original)
    assert parse_dataset_csv(updated)[0]["id"] == "old"
    assert parse_dataset_csv(updated)[1]["id"] == "new"


def test_append_handles_multiline_selftext_and_quotes():
    original = make_csv([sample_row("old")])
    new_row = sample_row("new", 'First line\nSecond line with "quotes"')

    updated = append_rows_to_csv_bytes(original, [new_row])
    rows = parse_dataset_csv(updated)

    assert rows[-1]["selftext"] == 'First line\nSecond line with "quotes"'


def test_append_ignores_transient_extra_fields():
    original = make_csv([sample_row("old")])
    new_row = sample_row("new") | {
        "matched_pain_keywords": ["blocked"],
        "matched_tools": ["jira"],
    }

    updated = append_rows_to_csv_bytes(original, [new_row])
    rows = parse_dataset_csv(updated)

    assert tuple(rows[-1].keys()) == DATASET_COLUMNS


def test_append_requires_all_dataset_columns():
    original = make_csv([sample_row("old")])
    new_row = sample_row("new")
    del new_row["author"]

    with pytest.raises(ValueError, match="missing required columns"):
        append_rows_to_csv_bytes(original, [new_row])


def test_append_no_rows_returns_identical_bytes():
    original = make_csv([sample_row("old")])

    assert append_rows_to_csv_bytes(original, []) is original


def test_append_preserves_crlf_newline_style():
    original = make_csv([sample_row("old")], lineterminator="\r\n")

    updated = append_rows_to_csv_bytes(original, [sample_row("new")])

    appended_part = updated[len(original) :]
    assert b"\r\n" in appended_part
