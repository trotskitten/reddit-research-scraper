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
global_search:
  enabled: true
matching:
  case_sensitive: false
""".strip(),
        encoding="utf-8",
    )


def test_pipeline_merges_unfiltered_subreddit_posts_with_global_search(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)

    snapshot = DatasetSnapshot(
        raw_bytes=b"subreddit,id,title,author,created_utc,created_iso,url,selftext\n",
        rows=[{"id": "existing", "selftext": "old body"}],
    )
    subreddit_posts = [{"post_id": "a"}, {"post_id": "b"}]
    global_posts = [{"post_id": "c", "matched_pain_keywords": ["blocked"], "matched_tools": ["jira"]}]
    cleaned_posts = [
        {"id": "a", "selftext": "one"},
        {"id": "b", "selftext": "two"},
        {"id": "c", "selftext": "three"},
    ]
    unique_posts = [{"id": "c", "selftext": "three"}]
    uploads = []
    clean_inputs = []

    monkeypatch.setattr(pipeline, "create_drive_service", lambda: "drive")
    monkeypatch.setattr(pipeline, "get_dataset_file_id", lambda: "file-id")
    monkeypatch.setattr(pipeline, "download_dataset", lambda service, file_id: snapshot)
    monkeypatch.setattr(pipeline, "create_reddit_client", lambda: "reddit")
    monkeypatch.setattr(
        pipeline,
        "scrape_posts",
        lambda reddit, subreddits, lookback_hours: subreddit_posts,
    )
    monkeypatch.setattr(
        pipeline,
        "search_reddit_by_keywords",
        lambda reddit, pain_keywords, tools, lookback_hours, case_sensitive=False: global_posts,
    )

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
        "append_rows_to_csv_bytes",
        lambda raw_bytes, rows: b"updated-dataset",
    )
    monkeypatch.setattr(
        pipeline,
        "upload_dataset",
        lambda service, file_id, raw_bytes: uploads.append((service, file_id, raw_bytes)),
    )

    result = pipeline.run_pipeline(config_path)

    assert clean_inputs == [subreddit_posts + global_posts]
    assert result.existing_rows == 1
    assert result.subreddit_posts == 2
    assert result.global_search_posts == 1
    assert result.combined_candidates == 3
    assert result.unique_posts == 1
    assert result.uploaded is True
    assert uploads == [("drive", "file-id", b"updated-dataset")]


def test_pipeline_does_not_keyword_filter_curated_subreddit_stream(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)

    snapshot = DatasetSnapshot(
        raw_bytes=b"subreddit,id,title,author,created_utc,created_iso,url,selftext\n",
        rows=[],
    )
    curated_post = {"post_id": "curated", "title": "No configured keywords here"}
    cleaned_post = {"id": "curated", "selftext": "ordinary subreddit post"}
    clean_inputs = []

    monkeypatch.setattr(pipeline, "create_drive_service", lambda: "drive")
    monkeypatch.setattr(pipeline, "get_dataset_file_id", lambda: "file-id")
    monkeypatch.setattr(pipeline, "download_dataset", lambda service, file_id: snapshot)
    monkeypatch.setattr(pipeline, "create_reddit_client", lambda: "reddit")
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
    monkeypatch.setattr(pipeline, "append_rows_to_csv_bytes", lambda raw_bytes, rows: b"updated")
    monkeypatch.setattr(pipeline, "upload_dataset", lambda service, file_id, raw_bytes: None)

    result = pipeline.run_pipeline(config_path)

    assert clean_inputs == [[curated_post]]
    assert result.subreddit_posts == 1
    assert result.global_search_posts == 0
    assert result.unique_posts == 1


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
        "search_reddit_by_keywords",
        lambda reddit, pain_keywords, tools, lookback_hours, case_sensitive=False: [],
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
    assert result.subreddit_posts == 0
    assert result.global_search_posts == 0
    assert result.combined_candidates == 0
    assert result.unique_posts == 0
    assert result.uploaded is False
    assert uploads == []


def test_dry_run_never_constructs_or_uploads_dataset(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)

    snapshot = DatasetSnapshot(
        raw_bytes=b"subreddit,id,title,author,created_utc,created_iso,url,selftext\n",
        rows=[],
    )
    curated_raw = {"post_id": "new-post"}
    unique_posts = [
        {
            "subreddit": "projectmanagement",
            "id": "new-post",
            "title": "Any ordinary recent post",
            "selftext": "No keyword requirement here",
        }
    ]

    monkeypatch.setattr(pipeline, "create_drive_service", lambda: "drive")
    monkeypatch.setattr(pipeline, "get_dataset_file_id", lambda: "file-id")
    monkeypatch.setattr(pipeline, "download_dataset", lambda service, file_id: snapshot)
    monkeypatch.setattr(pipeline, "create_reddit_client", lambda: "reddit")
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
        raise AssertionError("Drive write path must not be called during dry run")

    monkeypatch.setattr(pipeline, "append_rows_to_csv_bytes", fail_if_called)
    monkeypatch.setattr(pipeline, "upload_dataset", fail_if_called)

    result = pipeline.run_pipeline(config_path, dry_run=True)

    assert result.subreddit_posts == 1
    assert result.unique_posts == 1
    assert result.uploaded is False
