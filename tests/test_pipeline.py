from pathlib import Path

from reddit_scraper import pipeline
from reddit_scraper.sheets_storage import DatasetSnapshot


def write_config(path: Path) -> None:
    path.write_text(
        """
reddit:
  subreddit_lookback_hours: 13
  global_search_lookback_hours: 6
subreddits:
  - projectmanagement
pain_keywords:
  - blocked
tools:
  - jira
global_search:
  enabled: true
matching:
  case_sensitive: false
""".strip(),
        encoding="utf-8",
    )


def wire_common(monkeypatch, snapshot):
    monkeypatch.setenv("DATASET_STORAGE", "sheets")
    monkeypatch.setattr(pipeline, "create_sheets_service", lambda: "sheets")
    monkeypatch.setattr(
        pipeline,
        "get_dataset_spreadsheet_id",
        lambda: "spreadsheet-id",
    )
    monkeypatch.setattr(
        pipeline,
        "read_dataset",
        lambda service, spreadsheet_id: snapshot,
    )
    monkeypatch.setattr(pipeline, "create_reddit_client", lambda: "reddit")


def test_pipeline_merges_unfiltered_subreddit_posts_with_global_search(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)

    snapshot = DatasetSnapshot(rows=[{"id": "existing", "selftext": "old body"}])
    subreddit_posts = [{"post_id": "a"}, {"post_id": "b"}]
    global_posts = [{"post_id": "c", "matched_pain_keywords": ["blocked"], "matched_tools": ["jira"]}]
    cleaned_posts = [
        {"id": "a", "selftext": "one"},
        {"id": "b", "selftext": "two"},
        {"id": "c", "selftext": "three"},
    ]
    unique_posts = [{"id": "c", "selftext": "three"}]
    appends = []
    clean_inputs = []
    subreddit_calls = []
    global_calls = []

    wire_common(monkeypatch, snapshot)

    def fake_scrape(reddit, subreddits, lookback_hours):
        subreddit_calls.append((reddit, list(subreddits), lookback_hours))
        return subreddit_posts

    def fake_global(reddit, pain_keywords, tools, lookback_hours, case_sensitive=False):
        global_calls.append(
            (reddit, list(pain_keywords), list(tools), lookback_hours, case_sensitive)
        )
        return global_posts

    monkeypatch.setattr(pipeline, "scrape_posts", fake_scrape)
    monkeypatch.setattr(pipeline, "search_reddit_by_keywords", fake_global)

    def fake_clean(posts):
        clean_inputs.append(list(posts))
        return cleaned_posts

    monkeypatch.setattr(pipeline, "clean_posts", fake_clean)
    monkeypatch.setattr(
        pipeline,
        "deduplicate_posts",
        lambda new_posts, existing_posts: unique_posts,
    )
    monkeypatch.setattr(
        pipeline,
        "append_rows_to_sheet",
        lambda service, spreadsheet_id, rows: appends.append(
            (service, spreadsheet_id, list(rows))
        ) or len(unique_posts),
    )

    result = pipeline.run_pipeline(config_path)

    assert subreddit_calls == [("reddit", ["projectmanagement"], 13)]
    assert global_calls == [("reddit", ["blocked"], ["jira"], 6, False)]
    assert clean_inputs == [subreddit_posts + global_posts]
    assert result.existing_rows == 1
    assert result.subreddit_posts == 2
    assert result.global_search_posts == 1
    assert result.combined_candidates == 3
    assert result.unique_posts == 1
    assert result.uploaded is True
    assert appends == [("sheets", "spreadsheet-id", unique_posts)]


def test_pipeline_does_not_keyword_filter_curated_subreddit_stream(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)

    snapshot = DatasetSnapshot(rows=[])
    curated_post = {"post_id": "curated", "title": "No configured keywords here"}
    cleaned_post = {"id": "curated", "selftext": "ordinary subreddit post"}
    clean_inputs = []

    wire_common(monkeypatch, snapshot)
    monkeypatch.setattr(
        pipeline,
        "scrape_posts",
        lambda reddit, subreddits, lookback_hours: [curated_post],
    )
    monkeypatch.setattr(
        pipeline,
        "search_reddit_by_keywords",
        lambda reddit, pain_keywords, tools, lookback_hours, case_sensitive=False: [],
    )

    def fake_clean(posts):
        clean_inputs.append(list(posts))
        return [cleaned_post]

    monkeypatch.setattr(pipeline, "clean_posts", fake_clean)
    monkeypatch.setattr(
        pipeline,
        "deduplicate_posts",
        lambda new_posts, existing_posts: list(new_posts),
    )
    monkeypatch.setattr(
        pipeline,
        "append_rows_to_sheet",
        lambda service, spreadsheet_id, rows: len(list(rows)),
    )

    result = pipeline.run_pipeline(config_path)

    assert clean_inputs == [[curated_post]]
    assert result.subreddit_posts == 1
    assert result.global_search_posts == 0
    assert result.unique_posts == 1


def test_pipeline_does_not_write_when_no_unique_posts(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)

    snapshot = DatasetSnapshot(rows=[])
    appends = []

    wire_common(monkeypatch, snapshot)
    monkeypatch.setattr(pipeline, "scrape_posts", lambda reddit, subreddits, lookback_hours: [])
    monkeypatch.setattr(
        pipeline,
        "search_reddit_by_keywords",
        lambda reddit, pain_keywords, tools, lookback_hours, case_sensitive=False: [],
    )
    monkeypatch.setattr(pipeline, "clean_posts", lambda posts: [])
    monkeypatch.setattr(pipeline, "deduplicate_posts", lambda new_posts, existing_posts: [])
    monkeypatch.setattr(
        pipeline,
        "append_rows_to_sheet",
        lambda service, spreadsheet_id, rows: appends.append(rows),
    )

    result = pipeline.run_pipeline(config_path)

    assert result.existing_rows == 0
    assert result.subreddit_posts == 0
    assert result.global_search_posts == 0
    assert result.combined_candidates == 0
    assert result.unique_posts == 0
    assert result.uploaded is False
    assert appends == []


def test_dry_run_never_writes_sheet(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)

    snapshot = DatasetSnapshot(rows=[])
    curated_raw = {"post_id": "new-post"}
    unique_posts = [
        {
            "subreddit": "projectmanagement",
            "id": "new-post",
            "title": "Any ordinary recent post",
            "selftext": "No keyword requirement here",
        }
    ]

    wire_common(monkeypatch, snapshot)
    monkeypatch.setattr(
        pipeline,
        "scrape_posts",
        lambda reddit, subreddits, lookback_hours: [curated_raw],
    )
    monkeypatch.setattr(
        pipeline,
        "search_reddit_by_keywords",
        lambda reddit, pain_keywords, tools, lookback_hours, case_sensitive=False: [],
    )
    monkeypatch.setattr(pipeline, "clean_posts", lambda posts: unique_posts)
    monkeypatch.setattr(
        pipeline,
        "deduplicate_posts",
        lambda new_posts, existing_posts: unique_posts,
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Google Sheets write path must not be called during dry run")

    monkeypatch.setattr(pipeline, "append_rows_to_sheet", fail_if_called)

    result = pipeline.run_pipeline(config_path, dry_run=True)

    assert result.subreddit_posts == 1
    assert result.unique_posts == 1
    assert result.uploaded is False
