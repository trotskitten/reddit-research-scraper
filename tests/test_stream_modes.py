from pathlib import Path

from reddit_scraper import pipeline
from reddit_scraper.drive_storage import DatasetSnapshot


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


def setup_common(monkeypatch, snapshot):
    monkeypatch.setattr(pipeline, "create_drive_service", lambda: "drive")
    monkeypatch.setattr(pipeline, "get_dataset_file_id", lambda: "file-id")
    monkeypatch.setattr(pipeline, "download_dataset", lambda service, file_id: snapshot)
    monkeypatch.setattr(pipeline, "create_reddit_client", lambda: "reddit")
    monkeypatch.setattr(pipeline, "append_rows_to_csv_bytes", lambda raw_bytes, rows: b"updated")
    monkeypatch.setattr(pipeline, "upload_dataset", lambda service, file_id, raw_bytes: None)


def test_curated_stream_never_calls_global_search(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    snapshot = DatasetSnapshot(
        raw_bytes=b"subreddit,id,title,author,created_utc,created_iso,url,selftext\n",
        rows=[],
    )
    setup_common(monkeypatch, snapshot)

    curated_raw = {"post_id": "curated"}
    cleaned = {"id": "curated", "selftext": "body"}
    scrape_calls = []

    def fake_scrape(reddit, subreddits, lookback_hours):
        scrape_calls.append((reddit, list(subreddits), lookback_hours))
        return [curated_raw]

    def fail_global(*args, **kwargs):
        raise AssertionError("Global search must not run in curated-only mode")

    monkeypatch.setattr(pipeline, "scrape_posts", fake_scrape)
    monkeypatch.setattr(pipeline, "search_reddit_by_keywords", fail_global)
    monkeypatch.setattr(pipeline, "clean_posts", lambda posts: [cleaned])
    monkeypatch.setattr(pipeline, "deduplicate_posts", lambda new_posts, existing_posts: list(new_posts))

    result = pipeline.run_pipeline(config_path, stream="curated")

    assert scrape_calls == [("reddit", ["projectmanagement"], 13)]
    assert result.subreddit_posts == 1
    assert result.global_search_posts == 0
    assert result.unique_posts == 1


def test_global_stream_never_calls_curated_scraper(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    snapshot = DatasetSnapshot(
        raw_bytes=b"subreddit,id,title,author,created_utc,created_iso,url,selftext\n",
        rows=[],
    )
    setup_common(monkeypatch, snapshot)

    global_raw = {
        "post_id": "global",
        "matched_pain_keywords": ["blocked"],
        "matched_tools": ["jira"],
    }
    cleaned = {"id": "global", "selftext": "blocked in jira"}
    global_calls = []

    def fail_curated(*args, **kwargs):
        raise AssertionError("Curated scraper must not run in global-only mode")

    def fake_global(reddit, pain_keywords, tools, lookback_hours, case_sensitive=False):
        global_calls.append((reddit, list(pain_keywords), list(tools), lookback_hours, case_sensitive))
        return [global_raw]

    monkeypatch.setattr(pipeline, "scrape_posts", fail_curated)
    monkeypatch.setattr(pipeline, "search_reddit_by_keywords", fake_global)
    monkeypatch.setattr(pipeline, "clean_posts", lambda posts: [cleaned])
    monkeypatch.setattr(pipeline, "deduplicate_posts", lambda new_posts, existing_posts: list(new_posts))

    result = pipeline.run_pipeline(config_path, stream="global")

    assert global_calls == [("reddit", ["blocked"], ["jira"], 6, False)]
    assert result.subreddit_posts == 0
    assert result.global_search_posts == 1
    assert result.unique_posts == 1


def test_invalid_stream_is_rejected(tmp_path):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)

    try:
        pipeline.run_pipeline(config_path, stream="everything")
    except ValueError as exc:
        assert "Invalid stream" in str(exc)
    else:
        raise AssertionError("Invalid stream should raise ValueError")
