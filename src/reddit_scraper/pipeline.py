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
from reddit_scraper.matcher import filter_matching_posts
from reddit_scraper.scraper import create_reddit_client, scrape_posts

LOGGER = logging.getLogger(__name__)
DEFAULT_CONFIG_PATH = Path("config/config.yaml")


@dataclass(frozen=True)
class PipelineResult:
    """Counts produced by one completed pipeline run."""

    existing_rows: int
    scraped_posts: int
    matched_posts: int
    unique_posts: int
    uploaded: bool


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, object]:
    """Load and minimally validate the YAML pipeline configuration."""

    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    if not isinstance(config, dict):
        raise ValueError("Configuration root must be a mapping")

    required_keys = ("reddit", "subreddits", "pain_keywords", "tools", "matching")
    missing = [key for key in required_keys if key not in config]
    if missing:
        raise ValueError(f"Configuration is missing required keys: {missing}")

    reddit_config = config["reddit"]
    matching_config = config["matching"]
    if not isinstance(reddit_config, dict) or "lookback_hours" not in reddit_config:
        raise ValueError("Configuration must define reddit.lookback_hours")
    if not isinstance(matching_config, dict):
        raise ValueError("Configuration matching section must be a mapping")

    return config


def run_pipeline(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    dry_run: bool = False,
) -> PipelineResult:
    """Run one complete scrape/filter/deduplicate/store cycle.

    The Drive dataset is downloaded before scraping so the deduplication stage
    compares candidates against a fresh source-of-truth snapshot from the start
    of the run.

    When ``dry_run`` is true, the real Reddit and Drive reads still happen, but
    the pipeline never constructs replacement dataset bytes and never calls the
    Drive upload function. Unique candidates are logged for inspection instead.
    """

    config = load_config(config_path)

    drive_service = create_drive_service()
    dataset_file_id = get_dataset_file_id()
    snapshot = download_dataset(drive_service, dataset_file_id)
    LOGGER.info("Loaded %d existing dataset rows", len(snapshot.rows))

    reddit_client = create_reddit_client()
    reddit_config = config["reddit"]
    raw_posts = scrape_posts(
        reddit_client,
        config["subreddits"],
        int(reddit_config["lookback_hours"]),
    )
    LOGGER.info("Scraped %d recent Reddit posts", len(raw_posts))

    matching_config = config["matching"]
    matched_posts = filter_matching_posts(
        raw_posts,
        config["pain_keywords"],
        config["tools"],
        case_sensitive=bool(matching_config.get("case_sensitive", False)),
    )
    LOGGER.info("Matched %d posts against pain + tool rule", len(matched_posts))

    cleaned_posts = clean_posts(matched_posts)
    unique_posts = deduplicate_posts(cleaned_posts, snapshot.rows)
    LOGGER.info("Retained %d unique posts after deduplication", len(unique_posts))

    uploaded = False
    if dry_run:
        LOGGER.info("DRY RUN: Drive writes are disabled")
        for post in unique_posts:
            LOGGER.info(
                "DRY RUN candidate: r/%s | id=%s | %s",
                post.get("subreddit", ""),
                post.get("id", ""),
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
        scraped_posts=len(raw_posts),
        matched_posts=len(matched_posts),
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
        f"scraped={result.scraped_posts}, "
        f"matched={result.matched_posts}, "
        f"unique={result.unique_posts}, "
        f"uploaded={result.uploaded}"
    )


if __name__ == "__main__":
    main()
