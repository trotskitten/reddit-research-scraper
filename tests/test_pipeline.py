from pathlib import Path

from reddit_scraper import pipeline
from reddit_scraper.drive_storage import DatasetSnapshot


def write_config(path: Path) -> None:
    path.write_text(
        """
reddit:
  lookback_hours: 6
subreddits:
  - projectmanagement
pain_keywords:
  - blocked
tools:
  - jira
matching:
  case_sensitive: false
""".strip(),
        encoding="utf-8",
    )


def test_pipeline_uploads_only_unique_survivors(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)

    snapshot = DatasetSnapshot(
        raw_bytes=b"subreddit,id,title,author,created_utc,created_iso,url,selftext\n",
        rows=[{"id": "existing", "selftext": "old body"}],
    )
    raw_posts = [{"post_id": "a"}, {"post_id": "b"}, {"post_id": "c"}]
    matched_posts = [{"post_id": "a"}, {"post_id": "b"}]
    cleaned_posts = [{"id": "a", "selftext": "one"}, {"id": "b", "selftext": "two"}]
    unique_posts = [{"id": "b", "selftext": "two"}]
    uploads = []

    monkeypatch.setattr(pipeline, "create_drive_service", lambda: "drive")
    monkeypatch.setattr(pipeline, "get_dataset_file_id", lambda: "file-id")
    monkeypatch.setattr(pipeline, "download_dataset", lambda service, file_id: snapshot)
    monkeypatch.setattr(pipeline, "create_reddit_client", lambda: "reddit")
    monkeypatch.setattr(
        pipeline,
        "scrape_posts",
        lambda reddit, subreddits, lookback_hours: raw_posts,
    )
    monkeypatch.setattr(
        pipeline,
        "filter_matching_posts",
        lambda posts, pain_keywords, tools, case_sensitive=False: matched_posts,
    )
    monkeypatch.setattr(pipeline, "clean_posts", lambda posts: cleaned_posts)
    monkeypatch.setattr(
        pipeline,
        "deduplicate_posts",
        lambda new_posts, existing_posts: unique_posts,
    )
    monkeypatch.setattr(
        pipeline,
        "append_rows_to_csv_bytes",
        lambda raw_bytes, rows: b"updated-dataset",
    )
    monkeypatch.setattr(
        pipeline,
        "upload_dataset",
        lambda service, file_id, raw_bytes: uploads.append((service, file_id, raw_bytes)),
    )

    result = pipeline.run_pipeline(config_path)

    assert result.existing_rows == 1
    assert result.scraped_posts == 3
    assert result.matched_posts == 2
    assert result.unique_posts == 1
    assert result.uploaded is True
    assert uploads == [("drive", "file-id", b"updated-dataset")]


def test_pipeline_does_not_upload_when_no_unique_posts(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)

    snapshot = DatasetSnapshot(
        raw_bytes=b"subreddit,id,title,author,created_utc,created_iso,url,selftext\n",
        rows=[],
    )
    uploads = []

    monkeypatch.setattr(pipeline, "create_drive_service", lambda: "drive")
    monkeypatch.setattr(pipeline, "get_dataset_file_id", lambda: "file-id")
    monkeypatch.setattr(pipeline, "download_dataset", lambda service, file_id: snapshot)
    monkeypatch.setattr(pipeline, "create_reddit_client", lambda: "reddit")
    monkeypatch.setattr(pipeline, "scrape_posts", lambda reddit, subreddits, lookback_hours: [])
    monkeypatch.setattr(
        pipeline,
        "filter_matching_posts",
        lambda posts, pain_keywords, tools, case_sensitive=False: [],
    )
    monkeypatch.setattr(pipeline, "clean_posts", lambda posts: [])
    monkeypatch.setattr(pipeline, "deduplicate_posts", lambda new_posts, existing_posts: [])
    monkeypatch.setattr(
        pipeline,
        "upload_dataset",
        lambda service, file_id, raw_bytes: uploads.append((service, file_id, raw_bytes)),
    )

    result = pipeline.run_pipeline(config_path)

    assert result.existing_rows == 0
    assert result.scraped_posts == 0
    assert result.matched_posts == 0
    assert result.unique_posts == 0
    assert result.uploaded is False
    assert uploads == []
