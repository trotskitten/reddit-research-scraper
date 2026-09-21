from unittest.mock import Mock

import pytest

from reddit_scraper.sheets_storage import (
    DATASET_COLUMNS,
    LABEL_COLUMNS,
    append_rows_to_sheet,
    parse_sheet_values,
    prepare_rows_for_append,
)


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


def test_parse_sheet_values_returns_rows_and_restores_trailing_blanks():
    values = [list(DATASET_COLUMNS), list(sample_row().values())]

    rows = parse_sheet_values(values)

    assert len(rows) == 1
    assert rows[0]["id"] == "abc123"
    assert rows[0]["selftext"] == "Body text"
    assert all(rows[0][column] == "" for column in LABEL_COLUMNS)


def test_parse_sheet_values_rejects_unexpected_schema():
    with pytest.raises(ValueError, match="Unexpected dataset schema"):
        parse_sheet_values([["id", "title"], ["abc", "Example"]])


def test_prepare_rows_appends_blank_label_fields_and_ignores_transient_fields():
    row = sample_row("new") | {
        "matched_pain_keywords": ["blocked"],
        "matched_tools": ["jira"],
    }

    prepared = prepare_rows_for_append([row])

    assert len(prepared) == 1
    assert prepared[0][1] == "new"
    assert prepared[0][-len(LABEL_COLUMNS):] == [""] * len(LABEL_COLUMNS)


def test_prepare_rows_requires_all_source_columns():
    row = sample_row("new")
    del row["author"]

    with pytest.raises(ValueError, match="missing required columns"):
        prepare_rows_for_append([row])


def test_append_rows_uses_insert_rows_and_reports_count():
    execute = Mock(return_value={"updates": {"updatedRows": 1}})
    append = Mock()
    append.return_value.execute = execute
    values_api = Mock()
    values_api.append = append
    sheets_api = Mock()
    sheets_api.values.return_value = values_api
    service = Mock()
    service.spreadsheets.return_value = sheets_api

    appended = append_rows_to_sheet(
        service,
        "spreadsheet-id",
        [sample_row("new")],
        sheet_name="dataset",
    )

    assert appended == 1
    kwargs = append.call_args.kwargs
    assert kwargs["spreadsheetId"] == "spreadsheet-id"
    assert kwargs["range"] == "'dataset'!A:M"
    assert kwargs["valueInputOption"] == "RAW"
    assert kwargs["insertDataOption"] == "INSERT_ROWS"
    assert kwargs["body"]["values"][0][-len(LABEL_COLUMNS):] == [""] * len(LABEL_COLUMNS)


def test_append_no_rows_does_not_call_service():
    service = Mock()

    assert append_rows_to_sheet(service, "spreadsheet-id", []) == 0
    service.spreadsheets.assert_not_called()
