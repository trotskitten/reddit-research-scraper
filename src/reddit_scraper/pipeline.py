"""End-to-end Reddit research pipeline orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from reddit_scraper.cleaning import clean_posts
from reddit_scraper.deduplication import deduplicate_posts
from reddit_scraper.drive_storage import (
    append_rows_to_csv_bytes,
    create_drive_service,
    download_dataset,
    get_dataset_file_id,
    upload_dataset,
)
from reddit_scraper.global_search import search_reddit_by_keywords
from reddit_scraper.scraper import create_reddit_client, scrape_posts

LOGGER = logging.getLogger(__name__)
DEFAULT_CONFIG_PATH = Path("config/config.yaml")


@dataclass(frozen=True)
class PipelineResult:
    """Counts produced by one completed pipeline run."""

    existing_rows: int
    subreddit_posts: int
    global_search_posts: int
    combined_candidates: int
    unique_posts: int
    uploaded: bool


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, object]:
    """Load and minimally validate the YAML pipeline configuration."""

    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    if not isinstance(config, dict):
        raise ValueError("Configuration root must be a mapping")

    required_keys = (
        "reddit",
        "subreddits",
        "pain_keywords",
        "tools",
        "matching",
        "global_search",
    )
    missing = [key for key in required_keys if key not in config]
    if missing:
        raise ValueError(f"Configuration is missing required keys: {missing}")

    reddit_config = config["reddit"]
    matching_config = config["matching"]
    global_search_config = config["global_search"]

    if not isinstance(reddit_config, dict):
        raise ValueError("Configuration reddit section must be a mapping")

    required_reddit_keys = (
        "subreddit_lookback_hours",
        "global_search_lookback_hours",
    )
    missing_reddit = [
        key for key in required_reddit_keys if key not in reddit_config
    ]
    if missing_reddit:
        raise ValueError(
            f"Configuration reddit section is missing required keys: {missing_reddit}"
        )

    if not isinstance(matching_config, dict):
        raise ValueError("Configuration matching section must be a mapping")
    if not isinstance(global_search_config, dict):
        raise ValueError("Configuration global_search section must be a mapping")

    return config


def run_pipeline(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    dry_run: bool = False,
) -> PipelineResult:
    """Run one complete Reddit discovery/deduplicate/store cycle.

    There are two independent Reddit retrieval streams:

    1. Curated subreddit stream: every post from the configured subreddits in
       the subreddit lookback window is accepted without keyword filtering.
    2. Global search stream: r/all is searched using the configured pain + tool
       vocabulary and every returned post is locally verified to contain at
       least one pain term and at least one tool term within its own lookback.

    The two streams are merged before cleaning and deduplication against a fresh
    Google Drive dataset snapshot.

    When ``dry_run`` is true, all real reads still happen but the Drive write
    path is never called.
    """

    config = load_config(config_path)

    drive_service = create_drive_service()
    dataset_file_id = get_dataset_file_id()
    snapshot = download_dataset(drive_service, dataset_file_id)
    LOGGER.info("Loaded %d existing dataset rows", len(snapshot.rows))

    reddit_client = create_reddit_client()
    subreddit_lookback_hours = int(config["reddit"]["subreddit_lookback_hours"])
    global_search_lookback_hours = int(
        config["reddit"]["global_search_lookback_hours"]
    )

    subreddit_posts = scrape_posts(
        reddit_client,
        config["subreddits"],
        subreddit_lookback_hours,
    )
    LOGGER.info(
        "Curated subreddit scrape retained all %d recent posts without keyword filtering",
        len(subreddit_posts),
    )

    matching_config = config["matching"]
    global_search_config = config["global_search"]
    if bool(global_search_config.get("enabled", True)):
        global_search_posts = search_reddit_by_keywords(
            reddit_client,
            config["pain_keywords"],
            config["tools"],
            global_search_lookback_hours,
            case_sensitive=bool(matching_config.get("case_sensitive", False)),
        )
    else:
        global_search_posts = []

    LOGGER.info(
        "Global Reddit keyword search retained %d pain+tool posts",
        len(global_search_posts),
    )

    candidate_posts = subreddit_posts + global_search_posts
    cleaned_posts = clean_posts(candidate_posts)
    unique_posts = deduplicate_posts(cleaned_posts, snapshot.rows)
    LOGGER.info(
        "Merged %d candidates and retained %d unique posts after deduplication",
        len(candidate_posts),
        len(unique_posts),
    )

    uploaded = False
    if dry_run:
        LOGGER.info("DRY RUN: Drive writes are disabled")

        curated_ids = {str(post.get("post_id", "")) for post in subreddit_posts}
        global_by_id = {
            str(post.get("post_id", "")): post for post in global_search_posts
        }

        for post in unique_posts:
            post_id = str(post.get("id", ""))
            in_curated = post_id in curated_ids
            global_match = global_by_id.get(post_id)

            if in_curated and global_match is not None:
                source = "curated+global"
            elif in_curated:
                source = "curated"
            else:
                source = "global"

            LOGGER.info(
                "DRY RUN candidate: source=%s | r/%s | id=%s | pain=%s | tools=%s | %s",
                source,
                post.get("subreddit", ""),
                post_id,
                global_match.get("matched_pain_keywords", []) if global_match else [],
                global_match.get("matched_tools", []) if global_match else [],
                post.get("title", ""),
            )
    elif unique_posts:
        updated_bytes = append_rows_to_csv_bytes(snapshot.raw_bytes, unique_posts)
        upload_dataset(drive_service, dataset_file_id, updated_bytes)
        uploaded = True
        LOGGER.info("Appended %d posts to the Drive dataset", len(unique_posts))
    else:
        LOGGER.info("No unique posts to append; Drive dataset left unchanged")

    return PipelineResult(
        existing_rows=len(snapshot.rows),
        subreddit_posts=len(subreddit_posts),
        global_search_posts=len(global_search_posts),
        combined_candidates=len(candidate_posts),
        unique_posts=len(unique_posts),
        uploaded=uploaded,
    )


def main() -> None:
    """CLI entry point used by the live GitHub Actions pipeline."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = run_pipeline()
    print(
        "Pipeline complete: "
        f"existing={result.existing_rows}, "
        f"subreddits={result.subreddit_posts}, "
        f"global_search={result.global_search_posts}, "
        f"combined={result.combined_candidates}, "
        f"unique={result.unique_posts}, "
        f"uploaded={result.uploaded}"
    )


if __name__ == "__main__":
    main()
